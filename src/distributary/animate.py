# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Motion: the boot splash as it plays, the river flowing, the river growing.

Every renderer here reuses the stills' pieces (same geometry, palette, tone
curve and overlays), so a frame at rest is the wallpaper itself.
"""

import math
import multiprocessing
import os
import re
import subprocess

import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import raster, render, scene, svgout
from .raster import linear_to_srgb, srgb_to_linear, world_grid

# pulse shape q(theta) = cos^8(theta/2): a soft packet of light, and exactly
# four harmonics: (35 + 56 cos t + 28 cos 2t + 8 cos 3t + cos 4t) / 128
PULSE = (35 / 128, 56 / 128, 28 / 128, 8 / 128, 1 / 128)


def pulse(theta):
    return (0.5 * (1.0 + np.cos(theta))) ** 4


_LUMA32 = raster.LUMA.astype(np.float32)


def tonemap32(lin, knee):
    """raster.tonemap_sdr in float32: half the memory and time per 4K frame."""
    L = np.maximum(lin @ _LUMA32, np.float32(1e-8))
    span = np.float32(1.0 - knee)
    Lm = np.where(L > knee, knee + span * np.tanh((L - knee) / span), L)
    out = lin * (Lm / L)[..., None]
    mx = out.max(axis=-1)
    over = np.clip((mx - 1.0) / np.maximum(mx - Lm, 1e-6), 0, 1)[..., None]
    out += (Lm[..., None] - out) * over
    return np.clip(out, 0, 1, out=out)


# -- distance along the river --------------------------------------------------

def source_distance(branches):
    """Every centre-line point with its arc length from the source.

    Children start where their parent forks, so the distance runs on through
    every fork: a pulse that leaves the source splits at each junction.
    """
    by_id = {b["id"]: b for b in branches}
    offset = {}
    for b in sorted(branches, key=lambda b: b["id"]):   # parents come first
        par = by_id.get(b["parent"])
        offset[b["id"]] = 0.0 if par is None else offset.get(par["id"], 0.0) + par["s"][-1]
    pts = np.concatenate([np.column_stack([b["x"], b["y"]]) for b in branches])
    s = np.concatenate([offset[b["id"]] + b["s"] for b in branches])
    return pts, s, offset


def distance_map(view, pts, s, mask):
    """Arc length from the source for each masked pixel (nearest centre line)."""
    from scipy.spatial import cKDTree
    X, Y = world_grid(view)
    idx = np.nonzero(mask)
    _, j = cKDTree(pts).query(np.column_stack([X[idx], Y[idx]]), workers=-1)
    out = np.zeros(mask.shape, np.float32)
    out[idx] = s[j]
    return out


def overlay(svg_text, W, H):
    """An SVG layer on transparency: premultiplied sRGB RGBA, float32."""
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    surf = cairo.ImageSurface(cairo.Format.RGBA128F, W, H)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    Rsvg.Handle.new_from_data(svg_text.encode()).render_document(cairo.Context(surf), vp)
    surf.flush()
    return np.ndarray((H, surf.get_stride() // 16, 4), dtype=np.float32,
                      buffer=surf.get_data())[:, :W].copy()


def _over(dst, layer):
    """Composite a premultiplied RGBA layer over an RGB image, in place."""
    dst *= 1.0 - layer[..., 3:4]
    dst += layer[..., :3]
    return dst


# -- the river, flowing ----------------------------------------------------------

class Flow:
    """Pulses of light travelling downstream, splitting at every fork.

    The glow is a blur of the channels' light, and blurring is linear: the
    glow of a moving pulse train is a fixed mix of nine pre-blurred
    harmonic images.  So each frame costs a few multiply-adds, even at 4K.
    """

    def __init__(self, view, design, logo=None, wavelength=0.8, amplitude=0.7,
                 darken=0.3):
        pal = design.palette
        self.view, self.pal = view, pal
        self.amplitude, self.darken = amplitude, darken
        self.k = 2 * math.pi / wavelength
        X, Y = world_grid(view)
        vf = lambda p: p["value"]                       # noqa: E731
        order = lambda p: (p["value"], p.get("tint", 0.0))   # noqa: E731
        val, cov = raster.rasterize(design.pieces, view, vf, order_key=order,
                                    discs=design.forks)
        self.cov = cov
        self.wat = scene.water(X, Y, pal)
        if pal.source_tint:
            tval, _ = raster.rasterize(design.pieces, view, lambda p: p["tint"],
                                       order_key=order, discs=design.forks)
            t = np.where(cov > 1e-6, tval / np.maximum(cov, 1e-6), 0.0)[..., None]
            self.wat = scene.tinted(self.wat, t, pal)
        value = np.where(cov > 1e-6, val / np.maximum(cov, 1e-6), 1.0)
        self.chan_lin = scene.shade(self.wat, value[..., None], pal)
        pts, s, _ = source_distance(design.branches)
        self.dist = distance_map(view, pts, s, cov > 1e-5)
        land = scene.land(X, Y, pal)
        self.dark = pal.fade_to is None
        if self.dark:
            emis = self.wat * val[..., None]
            frac, core_blurs = pal.core
            core = None
            if core_blurs:
                cval, _ = raster.rasterize(design.pieces, view, vf, width_scale=frac,
                                           order_key=order, discs=design.forks)
                core = self.wat * cval[..., None]

            def glow_of(f):
                g = np.zeros_like(emis)
                for sigma, gain in pal.glow:
                    g += gain * raster.blur(emis * f, sigma * view.scale)
                for sigma, gain in (core_blurs if core is not None else ()):
                    g += gain * raster.blur(core * f, sigma * view.scale)
                return g
            self.land = land
            self.G = {(0, "c"): glow_of(1.0)}
            for n in range(1, len(PULSE)):
                ph = n * self.k * self.dist
                self.G[(n, "c")] = glow_of(np.cos(ph)[..., None])
                self.G[(n, "s")] = glow_of(np.sin(ph)[..., None])
        else:
            # light palettes: halos stain the paper and stay put; the ink pulses
            self.static_base, _ = scene.layers(view, design)
        W, H = view.W, view.H
        self.contours = overlay(svgout.document(view, design, parts={"contours"}), W, H)
        self.logo = None
        if logo:
            self.logo = overlay(svgout.document(view, design, logo=logo, parts={"logo"}), W, H)

    def frame(self, t, period, hdr=False, amp=1.0):
        """sRGB frame at time t (seconds) of a loop `period` seconds long.

        `amp` scales the pulses (0 = the still wallpaper), for ramping in.
        """
        pal = self.pal
        w = 2 * math.pi / period
        q = pulse(self.k * self.dist - w * t)[..., None]
        if self.dark:
            A = self.amplitude * amp
            glow = self.G[(0, "c")] * (1 + A * PULSE[0])
            for n in range(1, len(PULSE)):
                c, s_ = math.cos(n * w * t), math.sin(n * w * t)
                glow = glow + (A * PULSE[n]) * (self.G[(n, "c")] * c + self.G[(n, "s")] * s_)
            base_lin = self.land + glow
            chan = self.chan_lin * (1 + A * q)
        else:
            base_lin = self.static_base
            chan = self.chan_lin * (1 - self.darken * amp * q)
        out = linear_to_srgb(tonemap32(base_lin, pal.knee))
        _over(out, self.contours)
        a = (np.float32(pal.channel_opacity) * self.cov)[..., None]
        out = out * (1 - a) + a * linear_to_srgb(tonemap32(chan, pal.knee))
        if self.logo is not None:
            _over(out, self.logo)
        out = np.clip(out, 0, 1, out=out)
        if not hdr:
            return out, None
        scene_lin = base_lin * (1 - a) + a * chan
        resid = np.maximum(scene_lin - tonemap32(scene_lin, pal.knee), 0)
        return out, srgb_to_linear(out) + resid


# -- the river, growing from its source ------------------------------------------

class Growth:
    """The delta drawn by its own growth: channels appear in the order the
    water would reach them, tips tapering as they advance."""

    def __init__(self, view, design, logo=None):
        self.view, self.design, self.logo = view, design, logo
        # the distance by which everything inside the frame has appeared
        pts, s, _ = source_distance(design.branches)
        x0, y0 = view.to_px(pts[:, 0], pts[:, 1])
        inside = (x0 > -20) & (x0 < view.W + 20) & (y0 > -20) & (y0 < view.H + 20)
        self.s_enter = float(s[inside].min())
        self.s_full = float(s[inside].max())

    def frame(self, front, contour_fade=0.0, logo_fade=0.0):
        d = self.design.grown(front, contour_fade)
        logo = None
        if self.logo and logo_fade > 0:
            logo = dict(self.logo, opacity=self.logo.get("opacity", 1.0) * logo_fade)
        return render.render(self.view, d, logo=logo)["sdr"]


# -- boot screens, as they play -------------------------------------------------------

class PlymouthSim:
    """The Distributary Plymouth theme, following its script step by step.

    Layout, crossfade and the eased progress (x0.05 per 50 Hz refresh) are
    taken from distributary.script; text uses DejaVu Sans, the "Sans" of a
    Debian initramfs.
    """

    def __init__(self, theme_dir, W=1920, H=1080):
        self.W, self.H = W, H
        script = open(os.path.join(theme_dir, "distributary.script")).read()
        top = [float(v) for v in re.search(r"SetBackgroundTopColor \(([^)]*)\)", script).group(1).split(",")]
        bot = [float(v) for v in re.search(r"SetBackgroundBottomColor \(([^)]*)\)", script).group(1).split(",")]
        self.nframes = int(re.search(r"NB_FRAMES = (\d+);", script).group(1))
        y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        grad = np.array(top, np.float32) * (1 - y) + np.array(bot, np.float32) * y
        noise = np.random.default_rng(7).random((H, W, 1), dtype=np.float32) / 255.0
        self.bg = np.broadcast_to(grad, (H, W, 3)) + noise - 0.5 / 255.0

        def load(name):
            return Image.open(os.path.join(theme_dir, name)).convert("RGBA")

        def fit(im, mw, mh):
            return min(mw / im.width, mh / im.height)

        logo = load("logo.png")
        k = fit(logo, 0.48 * W, 0.060 * H)
        self.logo = logo.resize((round(logo.width * k), round(logo.height * k)), Image.BILINEAR)
        self.logo_xy = ((W - self.logo.width) // 2, round(0.33 * H - self.logo.height / 2))
        frames = [load(f"delta-{i}.png") for i in range(self.nframes)]
        k = fit(frames[0], 0.30 * W, 0.13 * H)
        size = (round(frames[0].width * k), round(frames[0].height * k))
        self.frames = [np.asarray(f.resize(size, Image.BILINEAR), np.float32) / 255 for f in frames]
        self.frame_xy = ((W - size[0]) // 2, round(0.435 * H - size[1] / 2))
        self.field = load("password_field.png")
        self.dot = load("password_dot.png")
        self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        l, t, r, b = self.font.getbbox("AfpqtM")
        self.line_h = b - t

    def image(self, shown, prompt=None, bullets=0):
        W, H = self.W, self.H
        pos = shown * (self.nframes - 1)
        k = min(int(pos), self.nframes - 1)
        frac = min(max(pos - k, 0.0), 1.0)
        img = self.bg.copy()
        x, y = self.frame_xy
        for idx, op in ((k, 1.0), (min(k + 1, self.nframes - 1), frac)):
            f = self.frames[idx]
            a = f[..., 3:4] * op
            region = img[y:y + f.shape[0], x:x + f.shape[1]]
            region *= 1 - a
            region += f[..., :3] * a
        out = Image.fromarray(np.clip(np.round(img * 255), 0, 255).astype(np.uint8))
        out.paste(self.logo, self.logo_xy, self.logo)
        if prompt:
            d = ImageDraw.Draw(out)
            top = 0.5 * H
            label_y = top + 3 * self.line_h                   # "action line" slot
            tw = d.textlength(prompt, font=self.font)
            d.text(((W - tw) / 2, label_y), prompt, font=self.font, fill=(255, 255, 255))
            ey = round(label_y + self.line_h * 1.5)
            ex = (W - self.field.width) // 2
            out.paste(self.field, (ex, ey), self.field)
            bw = self.dot.width
            spaces = int((self.field.width - 2 * bw) / (bw / 2))
            area_w = bw + spaces * (bw / 2)
            area_x = (W - area_w) / 2
            by = round(ey + self.field.height / 2 - self.dot.height / 2)
            for i in range(min(bullets, spaces)):
                out.paste(self.dot, (round(area_x + i * bw / 2), by), self.dot)
        return np.asarray(out, np.float32) / 255


def plymouth_timeline(sim, fps, scenario):
    """Yield (shown_progress, prompt, bullets) per video frame.

    scenario: list of (duration_s, target_start, target_end, prompt, typed)
    segments.  The script's easing runs at Plymouth's 50 Hz refresh.
    """
    shown, t_ref = 0.0, 0.0
    t = 0.0
    for dur, p0, p1, prompt, typed in scenario:
        n = round(dur * fps)
        for i in range(n):
            u = i / max(n - 1, 1)
            target = p0 + (p1 - p0) * u
            t += 1 / fps
            while t_ref < t:                     # 50 Hz refresh callbacks
                shown += (target - shown) * 0.05
                t_ref += 1 / 50
            bullets = 0
            if prompt and typed:
                # typed = (start, end, count): keys pressed evenly in between;
                # a segment whose window ended before it began is fully typed
                t0, t1, count = typed
                elapsed = i / fps
                done = 1.0 if elapsed >= t1 else max(0.0, (elapsed - t0) / (t1 - t0))
                bullets = int(done * count)
            yield shown, prompt, bullets


class GrubSim:
    """GRUB's default menu over the Distributary background."""

    ENTRIES = ["Debian GNU/Linux", "Advanced options for Debian GNU/Linux",
               "Memory test (memtest86+x64.efi)", "UEFI Firmware Settings"]

    def __init__(self, grub_png, W=1920, H=1080):
        self.bg = Image.open(grub_png).convert("RGB").resize((W, H), Image.LANCZOS)
        self.W, self.H = W, H
        self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 20)
        self.cw = self.font.getlength("M")

    def image(self, seconds_left):
        img = self.bg.copy()
        d = ImageDraw.Draw(img)
        cols = 80
        x0 = round((self.W - cols * self.cw) / 2)
        lh = 30
        top = round(self.H * 0.08)
        title = "GNU GRUB  version 2.12-9"
        d.text(((self.W - self.font.getlength(title)) / 2, top), title, font=self.font, fill=(255, 255, 255))
        box_top = top + 2 * lh
        box_bot = box_top + 12 * lh
        d.rectangle((x0, box_top, x0 + cols * self.cw, box_bot), outline=(255, 255, 255), width=2)
        for i, e in enumerate(self.ENTRIES):
            yy = box_top + 10 + i * lh
            if i == 0:
                d.rectangle((x0 + 6, yy - 2, x0 + cols * self.cw - 6, yy + lh - 6), fill=(255, 255, 255))
            d.text((x0 + 18, yy), ("*" if i == 0 else " ") + e, font=self.font,
                   fill=(0, 0, 0) if i == 0 else (255, 255, 255))
        help_lines = ["Use the ↑ and ↓ keys to select which entry is highlighted.",
                      "Press enter to boot the selected OS, `e' to edit the commands",
                      "before booting or `c' for a command-line."]
        if seconds_left is not None:
            help_lines.append(f"The highlighted entry will be executed automatically in {seconds_left}s.")
        for i, line in enumerate(help_lines):
            d.text((x0 + 30, box_bot + 20 + i * lh), line, font=self.font, fill=(255, 255, 255))
        return np.asarray(img, np.float32) / 255


# -- video files ---------------------------------------------------------------------

REC709_GAMMA = 2.4


def to_video_rgb16(srgb):
    """sRGB frame -> BT.1886 code values, so video players show the same light."""
    lin = srgb_to_linear(np.clip(srgb, 0, 1))
    v = np.power(lin, 1 / REC709_GAMMA)
    return np.round(v * 65535).astype("<u2")


def to_pq_rgb16(hdr_lin, peak_nits=1000.0):
    from .encode import hdr_to_pq
    return np.round(hdr_to_pq(hdr_lin, peak_nits) * 65535).astype("<u2")


def sdr_outputs(stem, W, H, fps):
    """ffmpeg outputs: 10-bit AV1 at full size, plus H.264 at <=1080p for
    players without AV1.  Names carry the real height: stem-2160p.mp4."""
    # tag in the filter chain (frame properties win over -color_* options)
    # and in each bitstream, so every player knows it is BT.709
    tag = ",setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
    mux = ["-movflags", "+faststart"]
    out = [(f"{stem}-{H}p.mp4",
            ["-vf", "zscale=m=709:r=limited:d=error_diffusion,format=yuv420p10le" + tag,
             "-c:v", "libsvtav1", "-preset", "5", "-crf", "22", "-g", str(fps * 4),
             "-svtav1-params", "color-primaries=1:transfer-characteristics=1:"
                               "matrix-coefficients=1:color-range=0"] + mux)]
    w = min(W, 1920)
    h = round(w * H / W / 2) * 2
    out.append((f"{stem}-{h}p-h264.mp4",
                ["-vf", f"zscale=w={w}:h={h}:f=spline36,"
                        "zscale=m=709:r=limited:d=error_diffusion,format=yuv420p" + tag,
                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "film",
                 "-profile:v", "high", "-g", str(fps * 2),
                 "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709"] + mux))
    return out


def hdr_outputs(stem, H, fps, maxcll, maxfall):
    """HDR10: HEVC Main10 and AV1 10-bit, PQ / BT.2020 with static metadata."""
    tags = ["-movflags", "+faststart"]
    md = "G(8500,39850)B(6550,2300)R(35400,14600)WP(15635,16450)L(10000000,1)"
    conv = ("zscale=m=2020_ncl:r=limited:d=error_diffusion,format=yuv420p10le,"
            "setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc:range=tv")
    return [
        (f"{stem}-{H}p-hdr-hevc.mp4",
         ["-vf", conv, "-c:v", "libx265", "-preset", "medium", "-crf", "16",
          "-x265-params", f"hdr10=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:"
                          f"colormatrix=bt2020nc:range=limited:master-display={md}:"
                          f"max-cll={round(maxcll)},{round(maxfall)}:log-level=error",
          "-tag:v", "hvc1", "-g", str(fps * 4)] + tags),
        (f"{stem}-{H}p-hdr.mp4",
         ["-vf", conv, "-c:v", "libsvtav1", "-preset", "5", "-crf", "22", "-g", str(fps * 4),
          "-svtav1-params",
          "enable-hdr=1:color-primaries=9:transfer-characteristics=16:matrix-coefficients=9:"
          "mastering-display=G(0.17,0.797)B(0.131,0.046)R(0.708,0.292)WP(0.3127,0.329)"
          f"L(1000,0.0001):content-light={round(maxcll)},{round(maxfall)}"] + tags),
    ]


LOSSLESS = ["-c:v", "ffv1", "-level", "3", "-slices", "16", "-slicecrc", "1",
            "-threads", "4", "-pix_fmt", "gbrp16le"]


def encode_from(src, outputs):
    """Encode each deliverable from a lossless intermediate, one at a time
    (several 4K encoders at once need more memory than a desktop has)."""
    env = dict(os.environ, SVT_LOG="1")
    for path, args in outputs:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src]
                       + args + [path], check=True, env=env)
    return [(p, os.path.getsize(p)) for p, _ in outputs]


class VideoWriter:
    """Feed raw 16-bit RGB frames to one ffmpeg run with several outputs."""

    def __init__(self, W, H, fps, outputs):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{W}x{H}",
               "-r", str(fps), "-i", "-"]
        for path, args in outputs:
            cmd += ["-map", "0:v"] + args + [path]
        self.paths = [p for p, _ in outputs]
        env = dict(os.environ, SVT_LOG="1")          # SVT-AV1: errors only
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=env)

    def write(self, rgb16):
        self.proc.stdin.write(np.ascontiguousarray(rgb16).tobytes())

    def close(self):
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed for {self.paths}")


# -- parallel frame rendering ----------------------------------------------------------

_WORKER = {}


def _init_worker(fn):
    _WORKER["fn"] = fn


def _call(arg):
    return _WORKER["fn"](arg)


def parallel_frames(fn, args, workers=None):
    """Map fn over args in forked workers (they share the precomputed state),
    yielding results in order."""
    workers = workers or max(1, min(os.cpu_count() or 1, 12))
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(workers, initializer=_init_worker, initargs=(fn,)) as pool:
        yield from pool.imap(_call, args, chunksize=2)
