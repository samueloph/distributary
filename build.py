#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Build every Distributary deliverable from source.

    ./build.py all            # everything below
    ./build.py svg            # desktop-base SVGs (wallpaper, lockscreen, login)
    ./build.py raster         # native-resolution PNG wallpapers (4K..8K)
    ./build.py hdr            # HDR masters: PQ PNG, EXR, AVIF, gain-map AVIF, JXL
    ./build.py grub plymouth installer previews
    ./build.py video          # animations into media/ (slow, not in "all")
    ./build.py website        # images for the showcase site in website/

    ./build.py editor         # data for the palette editor in website/editor/
    ./build.py switcher       # the colour options the main site can switch to

    ./build.py --draft ...    # 4K at most: no 5K/8K renders (and no videos)
    ./build.py --scheme forest all website
                              # a colour option from src/distributary/options.py,
                              # built whole into build/schemes/forest/, with its
                              # own site in sites/forest/
    ./build.py --palette my-colours.json all
                              # the same for a palette saved from the editor
    ./build.py --seed 7 all   # another river (the proposal uses seed 6)

Outputs go to build/.  Rendering is deterministic: same source, same pixels.
"""

import argparse
import dataclasses
import json
import os
import re
import shutil
import sys
import time
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import numpy as np  # noqa: E402

from distributary import design as D  # noqa: E402
from distributary import components, encode, render, scene, svgout  # noqa: E402
from distributary import logo as debian_logo  # noqa: E402
from distributary.geometry import View  # noqa: E402
from distributary.raster import linear_to_srgb, tonemap_sdr  # noqa: E402

THEME = "distributary"
TITLE = "Distributary"
AUTHOR = {"Name": "Samuel Henrique", "Email": "samueloph@debian.org"}
LICENSE = "GPL-2.0-or-later OR CC-BY-SA-4.0"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")
PREFIX = f"/usr/share/desktop-base/{THEME}-theme"

# Nominal SVG sizes.  An SVG is resolution independent, but GNOME and KDE
# pick a file by matching the screen's shape and load it at its nominal
# size, so 4K-class entries keep large screens sharp.
SVG_SIZES = [(1280, 1024), (1600, 1200), (1280, 800), (1920, 1200), (1920, 1080),
             (2560, 1080), (1080, 2160), (3840, 2400), (3840, 2160), (5120, 2160)]
# Native-resolution rasters (SDR PNG), and the HDR masters
# one render per screen shape, at the largest size offered for download
# (smaller sizes of the same shape are scaled down from it)
RASTER_SIZES = [(3840, 2160), (5120, 2880), (7680, 4320),      # 16:9
                (3840, 2400),                                  # 16:10
                (3000, 2000),                                  # 3:2
                (2560, 1664), (3024, 1964), (3456, 2234),      # MacBook Air 13", Pro 14", Pro 16"
                (2732, 2048), (2560, 2048),                    # 4:3, 5:4
                (3440, 1440), (3840, 1600), (5120, 2160),      # ultrawide
                (5120, 1440),                                  # 32:9
                (1440, 3120), (1440, 3200), (2160, 4320)]      # phones: 19.5:9, 20:9, 1:2
HDR_SIZES = [(3840, 2160), (7680, 4320), (3840, 2400), (5120, 2160)]

# set from the command line: a colour option to build instead of the default
# palettes, and draft mode (4K is enough to choose between designs)
SCHEME = None
DRAFT = False
MAIN = "forest"                 # the colour the plain build (no --scheme) makes
PAGE_OWN = "violet"             # the colour the showcase's own HTML and CSS describe
LOGO_SCALE = 1.0                # --logo-scale: the Debian lockup, larger or smaller
DOWNLOAD_KEY = MAIN             # build/downloads/<this>


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure(*parts):
    path = os.path.join(OUT, *parts)
    os.makedirs(path, exist_ok=True)
    return path


# -- framing ---------------------------------------------------------------

def view_for(W, H):
    if H > W:
        # portrait (phones): the river flows from the top of the screen
        return View(W=W, H=H, height=PORTRAIT_HEIGHT, rotate=90)
    # the delta reaches about x = 1.45; frames wider than 21:9 (32:9) slide
    # left, so it still meets the right edge and the stem grows longer
    half = 0.5 * W / H
    return View(W=W, H=H, cx=min(0.0, DELTA_REACH - half))


def world_box(view):
    """(x0, x1, y0, y1): the part of the world a view shows."""
    hw, hh = view.width / 2, view.height / 2
    if view.rotate == 90:          # screen across is world -y, screen down is world x
        return (view.cy - hh, view.cy + hh, -view.cx - hw, -view.cx + hw)
    return (view.cx - hw, view.cx + hw, view.cy - hh, view.cy + hh)


DELTA_REACH = 1.45
PORTRAIT_HEIGHT = 16 / 9     # a phone shows as much river, top to bottom, as 16:9 does across

# The lockup's left edge on landscapes, in frame heights: 0.085 in from the
# left.  Desktops that fill every screen with one picture (Xfce and LXDE use
# desktop-base's 1920x1080) crop 16:9 to fit 16:10 screens, so frames up to
# 16:9 keep it inside the 16:10 frame, 0.045 in from its edge (the editor
# reads this too)
LOGO_X = dict(edge=0.085, frame=16 / 10, inset=0.045, upto=1.79)


def logo_x(W, H):
    """The lockup's left edge on a landscape frame, in pixels."""
    r, q = W / H, LOGO_X
    return H * (max(q["edge"], (r - q["frame"]) / 2 + q["inset"]) if r <= q["upto"] else q["edge"])


def logo_for(W, H, des, scale=None):
    """The lockup on a wallpaper; it grows with --logo-scale from (x, y), the
    swirl's left edge (its centre on phones) at its vertical middle."""
    pal = des.palette
    k = LOGO_SCALE if scale is None else scale
    if H > W:
        return dict(x=W / 2, y=H * 0.935, height=0.0235 * H * k, anchor="middle",
                    colour=pal.logo_colour, opacity=pal.logo_opacity)
    # bottom left, with room above a bottom panel (KDE's floats ~52px up)
    return dict(x=logo_x(W, H), y=H * 0.88, height=0.035 * H * k,
                colour=pal.logo_colour, opacity=pal.logo_opacity)


def base_png(des, W, H, long_side=1280):
    """The smooth layer (land, haze, glow) embedded in the SVGs."""
    k = long_side / max(W, H)
    bw, bh = max(1, round(W * k)), max(1, round(H * k))
    base_lin, _ = scene.layers(view_for(bw, bh), des)
    return encode.png_bytes(linear_to_srgb(tonemap_sdr(base_lin, knee=des.palette.knee)))


def wallpaper_svg(des, W, H, logo=True):
    return svgout.document(view_for(W, H), des, base_png=base_png(des, W, H),
                           logo=logo_for(W, H, des) if logo else None,
                           title=f"{TITLE} ({des.palette.name}) — Debian 14")


# -- desktop-base SVGs ---------------------------------------------------------

def build_svg(variants=("dark", "light")):
    for name in variants:
        des = D.get(name)
        suffix = "" if name == "dark" else f"-{name}"
        img_dir = ensure(f"{THEME}-theme", f"wallpaper{suffix}", "contents", "images")
        for W, H in SVG_SIZES:
            path = os.path.join(img_dir, f"{W}x{H}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(wallpaper_svg(des, W, H))
            log(f"svg  {os.path.relpath(path, OUT)}  {os.path.getsize(path) / 1e3:.0f} kB")
        _write_wallpaper_metadata(f"wallpaper{suffix}", name)
        if name == "dark":
            _write_wallpaper_metadata("lockscreen", name, images_from="wallpaper")
    if "light" in variants:
        _write_adaptive()
    build_login()


def _write_adaptive():
    """Light/dark pairing: the light wallpaper in light styles, the dark one in dark styles.

    KDE Plasma: one package with contents/images (light) and
    contents/images_dark (dark), here symlinks so nothing is duplicated.
    GNOME: a gnome-background-properties entry with filename-dark.
    """
    d = ensure(f"{THEME}-theme", "wallpaper-adaptive", "contents")
    for link, target in (("images", "../../wallpaper-light/contents/images"),
                         ("images_dark", "../../wallpaper/contents/images")):
        path = os.path.join(d, link)
        if os.path.lexists(path):
            os.unlink(path)
        os.symlink(target, path)
    with open(os.path.join(os.path.dirname(d), "metadata.json"), "w") as f:
        json.dump({"KPlugin": {"Name": f"{TITLE} (light and dark)", "Id": f"{TITLE}Adaptive",
                               "License": LICENSE, "Authors": [AUTHOR]}}, f, indent=4)
        f.write("\n")
    g = ensure(f"{THEME}-theme", "gnome-background-properties")
    with open(os.path.join(g, f"{THEME}.xml"), "w") as f:
        f.write(f"""<?xml version="1.0"?>
<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">
<wallpapers>
  <wallpaper deleted="false">
    <name>{xml_escape(TITLE)}</name>
    <filename>{PREFIX}/wallpaper-light/gnome-background.xml</filename>
    <filename-dark>{PREFIX}/wallpaper/gnome-background.xml</filename-dark>
    <options>zoom</options>
    <shade_type>solid</shade_type>
    <pcolor>{D.get("dark").palette.land[1][1]}</pcolor>
    <scolor>{D.get("dark").palette.land[1][1]}</scolor>
  </wallpaper>
</wallpapers>
""")
    log("adaptive: KDE images/images_dark package, GNOME light/dark entry")


def _write_wallpaper_metadata(kind, variant, images_from=None):
    d = ensure(f"{THEME}-theme", kind)
    src = images_from or kind
    display = TITLE if variant == "dark" else f"{TITLE} {variant.title()}"
    with open(os.path.join(d, "metadata.json"), "w") as f:
        json.dump({"KPlugin": {"Name": display, "Id": display.replace(" ", ""),
                               "License": LICENSE, "Authors": [AUTHOR]}}, f, indent=4)
        f.write("\n")
    sizes = sorted(SVG_SIZES, key=lambda s: (s[0] * s[1], s))
    rows = "\n".join(f'      <size width="{W}" height="{H}">{PREFIX}/{src}/contents/'
                     f'images/{W}x{H}.svg</size>' for W, H in sizes)
    with open(os.path.join(d, "gnome-background.xml"), "w") as f:
        f.write("<background>\n  <static>\n    <duration>8640000.0</duration>\n"
                f"    <file>\n{rows}\n    </file>\n  </static>\n</background>\n")


# the login box sits in the middle: sink the delta below and to the right
LOGIN_WINDOW = dict(cx=-0.08, cy=-0.42, height=1.35)


def login_logo(W, H, des):
    """Login screens carry the lockup at the top centre, low enough to clear a
    greeter's top bar when a 16:9 screen crops this 16:10 picture (LightDM's
    GTK greeter zooms it, and its bar is about 25px tall)."""
    return dict(x=W / 2, y=H * 0.105, height=0.040 * H * LOGO_SCALE, anchor="middle",
                colour=des.palette.logo_colour, opacity=des.palette.logo_opacity)


def login_image(W, H):
    des = D.get("dark")
    return render.render(View(W=W, H=H, **LOGIN_WINDOW), des, logo=login_logo(W, H, des))["sdr"]


def build_login():
    des = D.get("dark")
    d = ensure(f"{THEME}-theme", "login")
    W, H = 1920, 1200
    for fname, logo in (("background.svg", True), ("background-nologo.svg", False)):
        lg = login_logo(W, H, des) if logo else None
        view = View(W=W, H=H, **LOGIN_WINDOW)
        k = 1280 / W
        base_lin, _ = scene.layers(View(W=round(W * k), H=round(H * k), **LOGIN_WINDOW), des)
        base = encode.png_bytes(linear_to_srgb(tonemap_sdr(base_lin, knee=des.palette.knee)))
        doc = svgout.document(view, des, base_png=base, logo=lg,
                              title=f"{TITLE} login — Debian 14")
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            f.write(doc)
        log(f"svg  {THEME}-theme/login/{fname}")


# -- rasters and HDR -----------------------------------------------------------

def _env_sizes():
    """SIZES="3000x2000 1440x3120" in the environment, as [(W, H), ...]."""
    return [tuple(int(n) for n in s.split("x")) for s in os.environ.get("SIZES", "").split()]


def build_raster(variants=("dark", "light"), sizes=None):
    """PNG wallpapers at RASTER_SIZES; SIZES="3000x2000 1440x3120" renders some."""
    sizes = sizes or _env_sizes()
    d = ensure("wallpapers")
    for name in variants:
        des = D.get(name)
        for W, H in sizes or RASTER_SIZES:
            t = time.time()
            r = render.render(view_for(W, H), des, logo=logo_for(W, H, des))
            path = os.path.join(d, f"{THEME}-{name}-{W}x{H}.png")
            encode.save_sdr_png(path, r["sdr"])
            log(f"png  {os.path.relpath(path, OUT)}  {os.path.getsize(path) / 1e6:.1f} MB"
                f"  ({time.time() - t:.0f}s)")


def build_hdr(sizes=None, peak=1000.0):
    """HDR masters at HDR_SIZES; SIZES="3840x2160" renders some."""
    sizes = sizes or _env_sizes()
    d = ensure("hdr")
    des = D.get("dark")
    for W, H in sizes or HDR_SIZES:
        t = time.time()
        r = render.render(view_for(W, H), des, logo=logo_for(W, H, des), hdr=True)
        stem = os.path.join(d, f"{THEME}-dark-{W}x{H}")
        pq_png = stem + "-hdr-pq.png"
        # smooth 16-bit SDR as the gain map's base (the 8-bit dithered PNG is
        # in wallpapers/; dither noise would only cost bits in a 10-bit AVIF)
        sdr_png = stem + "-sdr16.tmp.png"
        encode.save_sdr_png(sdr_png, r["sdr"], bits=16)
        maxcll, maxfall = encode.save_hdr_png(pq_png, r["hdr"], peak)
        made = ["hdr-pq.png"]
        if encode.have_module("OpenImageIO"):
            encode.save_exr(stem + "-linear.exr", r["hdr"])
            made.append("linear.exr")
        else:
            log("     (skipping EXR: install python3-openimageio)")
        if encode.have("avifenc"):
            encode.avif_pq(pq_png, stem + "-hdr-pq.avif", maxcll, maxfall)
            made.append("hdr-pq.avif")
        if encode.have("avifgainmaputil"):
            encode.avif_gainmap(sdr_png, pq_png, stem + "-gainmap.avif", maxcll, maxfall)
            made.append("gainmap.avif")
        if encode.have("cjxl"):
            encode.jxl_pq(pq_png, stem + "-hdr-pq.jxl")
            made.append("hdr-pq.jxl")
        os.unlink(sdr_png)
        with open(stem + "-hdr.json", "w") as f:
            json.dump({"MaxCLL": round(maxcll, 1), "MaxFALL": round(maxfall, 2),
                       "reference_white_nits": encode.REFERENCE_WHITE_NITS,
                       "mastering_peak_nits": peak,
                       "cicp": "9/16/0 (PNG) 9/16/9 (AVIF)"}, f, indent=2)
        log(f"hdr  {os.path.relpath(stem, OUT)}-{{{','.join(made)}}}  "
            f"MaxCLL {maxcll:.0f} MaxFALL {maxfall:.1f} nits  ({time.time() - t:.0f}s)")


# -- boot, login and installer -------------------------------------------------

def build_grub():
    d = ensure(f"{THEME}-theme", "grub")
    des = D.get("dark")
    for fname, (W, H) in (("grub-4x3.png", (1600, 1200)), ("grub-16x9.png", (1920, 1080))):
        path = os.path.join(d, fname)
        encode.save_sdr_png(path, components.grub(des, W, H))
        log(f"png  {os.path.relpath(path, OUT)}")
    with open(os.path.join(d, "grub_background.sh"), "w") as f:
        f.write("WALLPAPER=/usr/share/images/desktop-base/desktop-grub.png\n"
                "COLOR_NORMAL=white/black\nCOLOR_HIGHLIGHT=black/white\n")


def _save_rgba(path, rgba):
    from PIL import Image
    q = np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8)
    Image.fromarray(q, "RGBA").save(path, optimize=True)


def build_plymouth():
    d = ensure(f"{THEME}-theme", "plymouth")
    des = D.get("dark")
    pal = des.palette
    # the lockup, drawn at 4K size; the script only ever scales it down
    H = 128
    svg, width = components.lockup_svg(4000, H, 0.78 * H, colour="#ffffff")   # swirl + debian
    rgba = components.svg_rgba(svg, 4000, H)
    cols = np.flatnonzero(rgba[..., 3].max(axis=0) > 0)
    _save_rgba(os.path.join(d, "logo.png"), rgba[:, max(0, cols[0] - 4):cols[-1] + 5])
    frames = components.progress_frames(des, W=840, H=210, frames=20)
    for i, fr in enumerate(frames):
        _save_rgba(os.path.join(d, f"delta-{i}.png"), fr)
    components.password_field().write_to_png(os.path.join(d, "password_field.png"))
    components.password_dot().write_to_png(os.path.join(d, "password_dot.png"))
    top, bottom = pal.land[0][1], pal.land[-1][1]

    def rgb(hexcol):
        h = hexcol.lstrip("#")
        return ", ".join(f"{int(h[i:i + 2], 16) / 255:.4f}" for i in (0, 2, 4))
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plymouth",
                            f"{THEME}.script.in")).read()
    src = (src.replace("@TOP@", rgb(top)).replace("@BOTTOM@", rgb(bottom))
              .replace("@TOPHEX@", top).replace("@BOTTOMHEX@", bottom))
    with open(os.path.join(d, f"{THEME}.script"), "w") as f:
        f.write(src)
    with open(os.path.join(d, f"{THEME}.plymouth"), "w") as f:
        f.write(f"""[Plymouth Theme]
Name=Distributary theme for Debian 14 Forky
Description=Distributary theme by Samuel Henrique
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/{THEME}
ScriptFile=/usr/share/plymouth/themes/{THEME}/{THEME}.script
""")
    total = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
    log(f"plymouth theme: {len(os.listdir(d))} files, {total / 1e3:.0f} kB")


def build_installer():
    """debian-installer's banner and boot menu splash.  d-i builds its PNGs
    from these SVGs (rsvg-convert), so the PNGs here are librsvg's renders."""
    d = ensure("debian-installer")
    des = D.get("dark")
    pal = des.palette

    def svg_and_png(name, win, W, H, lg, title, scrim=None):
        base_lin, _ = scene.layers(View(W=W * 2, H=H * 2, **win), des)
        base = encode.png_bytes(linear_to_srgb(tonemap_sdr(base_lin, knee=pal.knee)))
        path = os.path.join(d, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svgout.document(View(W=W, H=H, **win), des, base_png=base, logo=lg,
                                    scrim=scrim, title=f"{TITLE} {title} — Debian 14"))
        _save_png(_rsvg_png(path, W, H), os.path.join(d, f"{name}.png"))

    # banner, 800x75: a slice of the river with the first fork at ~70% of the
    # width, the lockup on the calm left side.  d-i writes its own white label
    # on it ("Rescue mode"), so its light and dark themes both get this dark
    # banner, as in Trixie.  On wider screens d-i stretches the banner's first
    # and last columns, so the river fades into the land before the right
    # edge, as the left side does behind the lockup
    W, H = 800, 75
    lg = dict(x=0.045 * W, y=H / 2, height=0.42 * H, colour=pal.logo_colour,
              opacity=0.95, descriptor=debian_logo.DESCRIPTOR)
    for name in ("logo_installer", "logo_installer_dark"):
        svg_and_png(name, dict(cx=-0.88, cy=0.04, height=0.26), W, H, lg, "installer banner",
                    scrim=[(0.40 * W, 0.62 * W, 0.92), (W, 0.775 * W, 1.0)])
    log("svg  debian-installer/logo_installer{,_dark}.{svg,png} (800x75)")
    # boot menu splash of the installation media (isolinux / GRUB), 640x480:
    # lockup on top, the river kept low under the menu
    W, H = 640, 480
    lg = dict(x=W / 2, y=H * 0.10, height=0.05 * H, anchor="middle",
              colour=pal.logo_colour, opacity=0.9)
    svg_and_png("splash", dict(cx=-0.05, cy=-0.30, height=1.30), W, H, lg,
                "installer boot splash")
    log("svg  debian-installer/splash.{svg,png} (640x480)")


def build_banners():
    """debian.org / wiki banners, as SVG sources plus 2x PNG renders."""
    d = ensure("banners")
    des = D.get("dark")
    pal = des.palette
    specs = [
        # name, size, window onto the river, lockup, corner radius
        ("website-banner", (800, 119), dict(cx=-0.93, cy=0.04, height=0.41),
         dict(x=0.045 * 800, y=119 / 2, height=0.30 * 119, descriptor=debian_logo.DESCRIPTOR), 0),
        ("wiki-banner", (380, 380), dict(cx=-0.02, cy=0.03, height=1.05),
         dict(x=190, y=380 * 0.86, height=0.075 * 380, anchor="middle",
              descriptor=debian_logo.DESCRIPTOR), 24),
    ]
    for name, (W, H), win, lg, radius in specs:
        lg.update(colour=pal.logo_colour, opacity=pal.logo_opacity)
        view = View(W=W, H=H, **win)
        base_lin, _ = scene.layers(View(W=W * 2, H=H * 2, **win), des)
        base = encode.png_bytes(linear_to_srgb(tonemap_sdr(base_lin, knee=pal.knee)))
        scrim = (0.40 * W, 0.62 * W, 0.92) if name == "website-banner" else None
        doc = svgout.document(view, des, base_png=base, logo=lg, corner_radius=radius,
                              title=f"{TITLE} — Debian 14 {name.replace('-', ' ')}",
                              scrim=scrim)
        with open(os.path.join(d, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(doc)
        # PNG at 2x, rendered from the same document by librsvg
        view2 = View(W=W * 2, H=H * 2, **win)
        lg2 = {k: (v * 2 if k in ("x", "y", "height") else v) for k, v in lg.items()}
        r = render.render(view2, des, logo=lg2,
                          scrim=tuple(v * 2 for v in scrim[:2]) + scrim[2:] if scrim else None)
        rgb = r["sdr"]
        if radius:
            from PIL import Image, ImageDraw
            mask = Image.new("L", (W * 2, H * 2), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, W * 2 - 1, H * 2 - 1),
                                                   radius * 2, fill=255)
            rgba = np.dstack([rgb, np.asarray(mask, dtype=np.float32) / 255])
            _save_rgba(os.path.join(d, f"{name}@2x.png"), rgba)
        else:
            encode.save_sdr_png(os.path.join(d, f"{name}@2x.png"), rgb)
        log(f"banner {name} ({W}x{H} SVG, {W * 2}x{H * 2} PNG)")


def _rsvg_png(svg_path, W, H):
    """Render a shipped SVG exactly as GNOME would (librsvg, 8-bit)."""
    import cairo
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    h = Rsvg.Handle.new_from_file(svg_path)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    h.render_document(cairo.Context(surf), vp)
    surf.flush()
    from PIL import Image
    a = np.ndarray((H, surf.get_stride() // 4, 4), dtype=np.uint8,
                   buffer=surf.get_data())[:, :W, [2, 1, 0]]
    return Image.fromarray(np.array(a))


def _save_png(img, path):
    """An 8-bit image as PNG, tagged sRGB like the theme's other PNGs."""
    from PIL import PngImagePlugin
    info = PngImagePlugin.PngInfo()
    info.add(b"sRGB", b"\x00")
    img.save(path, pnginfo=info, compress_level=9)


def build_previews():
    from PIL import Image, ImageDraw, ImageFont
    d = ensure("previews")
    theme = os.path.join(OUT, f"{THEME}-theme")
    need = os.path.join(theme, "wallpaper", "contents", "images", "1920x1080.svg")
    if not os.path.exists(need):
        build_svg()
    for name, sub in (("dark", "wallpaper"), ("light", "wallpaper-light")):
        img = _rsvg_png(os.path.join(theme, sub, "contents", "images", "1920x1080.svg"),
                        1920, 1080)
        img.save(os.path.join(d, f"wallpaper-{name}.png"), optimize=True)
        if name == "dark":
            img.resize((550, 309), Image.LANCZOS).save(os.path.join(d, "thumb.png"))
    _rsvg_png(os.path.join(theme, "login", "background.svg"), 1920, 1200).save(
        os.path.join(d, "login.png"), optimize=True)

    # every aspect ratio, as shipped: landscapes in a grid, the phone on the right
    font = ImageFont.truetype("/usr/share/fonts/truetype/lato/Lato-Regular.ttf", 20)
    layout = [((1280, 1024), (20, 20, 330)), ((1600, 1200), (455, 20, 330)),
              ((1920, 1200), (930, 20, 330)), ((1920, 1080), (20, 400, 330)),
              ((2560, 1080), (640, 400, 330)), ((1080, 2160), (1470, 20, 710))]
    for name, sub in (("dark", "wallpaper"), ("light", "wallpaper-light")):
        dark = name == "dark"
        sheet = Image.new("RGB", (1850, 790), (40, 40, 44) if dark else (225, 225, 230))
        draw = ImageDraw.Draw(sheet)
        for (W, H), (x, y, h) in layout:
            w = round(h * W / H)
            img = _rsvg_png(os.path.join(theme, sub, "contents", "images", f"{W}x{H}.svg"), w, h)
            sheet.paste(img, (x, y))
            draw.text((x, y + h + 8), f"{W}x{H}", font=font,
                      fill=(230, 230, 235) if dark else (40, 40, 50))
        sheet.save(os.path.join(d, f"ratios-{name}.png"), optimize=True)

    # GRUB, with a menu drawn on top to show that it stays readable
    g = Image.open(os.path.join(theme, "grub", "grub-16x9.png")).convert("RGB")
    draw = ImageDraw.Draw(g)
    mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 22)
    draw.rectangle((240, 180, 1680, 560), outline=(255, 255, 255), width=2)
    entries = ["Debian GNU/Linux", "Advanced options for Debian GNU/Linux",
               "Memory test (memtest86+x64.efi)", "UEFI Firmware Settings"]
    for i, e in enumerate(entries):
        yy = 200 + i * 34
        if i == 0:
            draw.rectangle((250, yy - 2, 1670, yy + 28), fill=(255, 255, 255))
        draw.text((262, yy), e, font=mono, fill=(0, 0, 0) if i == 0 else (255, 255, 255))
    draw.text((250, 600), "Use the ^ and v keys to select which entry is highlighted.",
              font=mono, fill=(255, 255, 255))
    g.save(os.path.join(d, "grub.png"), optimize=True)

    # Plymouth: static mock-up and the boot animation
    ply = os.path.join(theme, "plymouth")

    def splash(W, H, frame, blend=0.0):
        top = np.array([int(D.get("dark").palette.land[0][1][i:i + 2], 16) for i in (1, 3, 5)])
        bot = np.array([int(D.get("dark").palette.land[-1][1][i:i + 2], 16) for i in (1, 3, 5)])
        t = np.linspace(0, 1, H)[:, None, None]
        img = Image.fromarray((top * (1 - t) + bot * t).round().astype(np.uint8).repeat(W, axis=1))

        def fit(im, mw, mh):
            k = min(mw / im.width, mh / im.height)
            return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        logo = fit(Image.open(os.path.join(ply, "logo.png")), 0.48 * W, 0.060 * H)
        img.paste(logo, ((W - logo.width) // 2, round(0.33 * H - logo.height / 2)), logo)
        for k, op in ((frame, 1.0), (min(frame + 1, 19), blend)):
            fr = fit(Image.open(os.path.join(ply, f"delta-{k}.png")), 0.30 * W, 0.13 * H)
            if op < 1:
                a = np.asarray(fr).copy()
                a[..., 3] = (a[..., 3] * op).astype(np.uint8)
                fr = Image.fromarray(a)
            img.paste(fr, ((W - fr.width) // 2, round(0.435 * H - fr.height / 2)), fr)
        return img
    splash(1920, 1080, 19).save(os.path.join(d, "plymouth.png"), optimize=True)
    # the first frame is the finished splash, so stills and thumbnails show it
    frames = [splash(960, 540, 19)]
    for i in range(0, 61):
        pos = i / 60 * 19
        frames.append(splash(960, 540, int(pos), pos - int(pos)))
    # an animated PNG: the wiki (MoinMoin) shows PNGs inline, but not WebP
    frames[0].save(os.path.join(d, "plymouth-boot.png"), save_all=True,
                   append_images=frames[1:], duration=[1500] + [50] * 60 + [1500],
                   loop=0, optimize=True)

    # the banner on the installer's light and dark themes
    from distributary import mockups
    banner = Image.open(os.path.join(OUT, "debian-installer", "logo_installer.png"))
    s = Image.new("RGB", (800 * 2 + 10, 600), (128, 128, 128))
    s.paste(mockups.installer(banner, scale=1), (0, 0))
    s.paste(mockups.installer(banner, dark=True, scale=1), (810, 0))
    s.save(os.path.join(d, "installer.png"), optimize=True)
    log(f"previews: {', '.join(sorted(os.listdir(d)))}")


MEDIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")


def build_video(which=None):
    """Videos into media/ (tracked in git).  Slow: not part of `all`.

    VIDEOS="flow-dark river-growth" ./build.py video renders a subset.
    """
    if DRAFT:
        log("video: skipped in draft mode")
        return
    which = which or (os.environ.get("VIDEOS", "").split() or None)
    from distributary import videos
    theme = os.path.join(OUT, f"{THEME}-theme")
    if not os.path.exists(os.path.join(theme, "plymouth", "logo.png")):
        build_plymouth()
    if not os.path.exists(os.path.join(theme, "grub", "grub-16x9.png")):
        build_grub()
    # the main theme's videos live in media/, a colour option's next to its pictures
    out = MEDIA if SCHEME is None else os.path.join(WEBSITE, "media")
    videos.build(out, os.path.join(OUT, "video-tmp"), theme, login_image, logo_for, which)


WEBSITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "website")
EDITOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "website", "editor")


def build_website():
    """Images for the showcase site (website/index.html is hand-written).

    With --scheme, that colour option's pictures and video posters, in
    website/schemes/<scheme>/img/, for the page's Colours switcher; the
    README's pictures and the colour option previews belong to the main site.
    """
    import subprocess
    from PIL import Image
    from distributary import animate, mockups, videos
    img_dir = os.path.join(WEBSITE, "img")
    os.makedirs(img_dir, exist_ok=True)
    theme = os.path.join(OUT, f"{THEME}-theme")
    # 1:1 detail crops come from the largest 16:9 render
    big = max((s for s in RASTER_SIZES if s[0] * 9 == s[1] * 16), key=lambda s: s[0])
    need = {
        "svg": os.path.join(theme, "wallpaper", "contents", "images", "1920x1080.svg"),
        "raster": os.path.join(OUT, "wallpapers", f"{THEME}-dark-{big[0]}x{big[1]}.png"),
        "hdr": os.path.join(OUT, "hdr", f"{THEME}-dark-3840x2160-linear.exr"),
        "grub": os.path.join(theme, "grub", "grub-16x9.png"),
        "plymouth": os.path.join(theme, "plymouth", "logo.png"),
        "installer": os.path.join(OUT, "debian-installer", "logo_installer.png"),
    }
    for target, path in need.items():
        if not os.path.exists(path):
            TARGETS[target]()

    def save(im, name, quality=90):
        path = os.path.join(img_dir, name)
        if name.endswith(".png"):
            im.save(path, optimize=True)
        else:
            im.convert("RGB").save(path, quality=quality, optimize=True, progressive=True,
                                   subsampling=0)
        return path

    wp = os.path.join(OUT, "wallpapers")
    dark4k = Image.open(os.path.join(wp, f"{THEME}-dark-3840x2160.png"))
    light4k = Image.open(os.path.join(wp, f"{THEME}-light-3840x2160.png"))
    # hero: the dark still is the HDR gain-map AVIF, with an SDR fallback
    shutil.copy(os.path.join(OUT, "hdr", f"{THEME}-dark-3840x2160-gainmap.avif"),
                os.path.join(img_dir, "hero-dark.gainmap.avif"))
    save(dark4k.resize((2400, 1350), Image.LANCZOS), "hero-dark.jpg")
    save(light4k.resize((2400, 1350), Image.LANCZOS), "hero-light.jpg")
    dark_hd = dark4k.resize((1920, 1080), Image.LANCZOS)
    light_hd = light4k.resize((1920, 1080), Image.LANCZOS)

    # in use
    svg, _ = components.lockup_svg(400, 160, 150, colour="#ffffff", wordmark=False)
    swirl = Image.fromarray(np.clip(np.round(components.svg_rgba(svg, 400, 160) * 255), 0, 255)
                            .astype(np.uint8), "RGBA")
    swirl = swirl.crop(swirl.getbbox())
    save(mockups.gnome(light_hd), "mock-gnome.jpg")
    save(mockups.gnome(dark_hd, terminal=True), "mock-gnome-dark.jpg")
    save(mockups.plasma(dark_hd, swirl), "mock-kde.jpg")
    login = Image.fromarray(np.clip(np.round(login_image(1920, 1080) * 255), 0, 255).astype(np.uint8))
    save(mockups.gdm(login), "mock-login.jpg")
    grub = animate.GrubSim(need["grub"]).image(5)
    save(Image.fromarray(np.round(grub * 255).astype(np.uint8)), "mock-grub.jpg")
    di = os.path.join(OUT, "debian-installer")
    save(mockups.installer(Image.open(os.path.join(di, "logo_installer.png"))), "mock-installer.png")
    save(mockups.installer(Image.open(os.path.join(di, "logo_installer_dark.png")), dark=True),
         "mock-installer-dark.png")

    # boot splash stills, from the same simulation as the video
    sim = animate.PlymouthSim(os.path.join(theme, "plymouth"), 1920, 1080)
    for i, p in enumerate((0.0, 0.5, 1.0)):
        save(Image.fromarray(np.round(sim.image(p) * 255).astype(np.uint8)), f"mock-plymouth-{i}.jpg")
    prompt = sim.image(0.05, prompt=videos.PASSPHRASE, bullets=9)
    save(Image.fromarray(np.round(prompt * 255).astype(np.uint8)), "mock-plymouth-3.jpg")

    # every screen shape, as shipped, side by side
    from PIL import ImageDraw, ImageFont
    h = 480
    shapes = [(2560, 1080, "21:9"), (1920, 1080, "16:9"), (1920, 1200, "16:10"),
              (1600, 1200, "4:3"), (1280, 1024, "5:4"), (1080, 2160, "phone")]
    tiles = [(_rsvg_png(os.path.join(theme, "wallpaper", "contents", "images", f"{w}x{hh}.svg"),
                        round(h * w / hh), h), label) for w, hh, label in shapes]
    # on the page's ground, labelled in its muted text colour
    if (SCHEME or MAIN) == PAGE_OWN:
        ground, muted = (11, 11, 34), (169, 159, 194)      # the page's own, hand-set tokens
    else:
        land = D.get("dark").palette.land[1][1]
        ground = tuple(int(land[i:i + 2], 16) for i in (1, 3, 5))
        muted = tuple(round(0.62 * 255 + 0.38 * c) for c in ground)
    strip = Image.new("RGB", (sum(t.width for t, _ in tiles) + 24 * (len(tiles) - 1), h + 44),
                      ground)
    dr = ImageDraw.Draw(strip)
    fnt = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 20)
    x = 0
    for t, label in tiles:
        strip.paste(t, (x, 0))
        dr.text((x, h + 12), label, font=fnt, fill=muted)
        x += t.width + 24
    save(strip, "aspect-ratios.jpg", quality=88)

    # 1:1 crops of the largest render: deep in the delta, and the first fork
    full = Image.open(need["raster"])
    tag = f"{round(big[0] / 960)}k"
    for name, (fx, fy) in (("delta", (5320 / 7680, 1780 / 4320)),
                           ("fork", (2400 / 7680, 2360 / 4320))):
        cx, cy = round(fx * full.width), round(fy * full.height)
        save(full.crop((cx - 700, cy - 400, cx + 700, cy + 400)), f"detail-{tag}-{name}.jpg",
             quality=92)

    # HDR: false-colour luminance and the numbers behind it
    import OpenImageIO as oiio
    lin = oiio.ImageBuf(need["hdr"]).get_pixels(oiio.FLOAT)[..., :3]
    lum_img, Y = mockups.luminance_map(lin)
    save(lum_img.resize((1920, 1080), Image.LANCZOS), "hdr-luminance.jpg")
    meta = json.load(open(os.path.join(OUT, "hdr", f"{THEME}-dark-3840x2160-hdr.json")))
    info = subprocess.run(["avifgainmaputil", "printmetadata",
                           os.path.join(img_dir, "hero-dark.gainmap.avif")],
                          capture_output=True, text=True, check=True).stdout
    headroom = float(info.split("Alternate headroom:")[1].split()[0])
    stats = mockups.hdr_stats(Y, meta["MaxCLL"], headroom)
    with open(os.path.join(img_dir, "hdr-stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
        f.write("\n")

    # a poster for each video: a frame from it, counted from its end when negative
    media = MEDIA if SCHEME is None else os.path.join(WEBSITE, "media")
    for name, src, t in (("poster-boot", "boot-to-desktop-1080p-h264.mp4", -1.0),
                         ("poster-plymouth", "plymouth-boot-1080p-h264.mp4", 12.6),
                         ("poster-growth", "river-growth-1080p-h264.mp4", 4.5)):
        if not os.path.exists(os.path.join(media, src)):
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-sseof" if t < 0 else "-ss", str(t), "-i",
                              os.path.join(media, src), "-frames:v", "1", "-vf", "format=rgb24",
                              "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        save(Image.frombytes("RGB", (1920, 1080), raw).resize((1280, 720), Image.LANCZOS),
             f"{name}.jpg", quality=86)
    if SCHEME is None:
        _website_main_extras(img_dir, save)
    files = [os.path.join(dp, f) for dp, _, fs in os.walk(img_dir) for f in fs]
    total = sum(os.path.getsize(f) for f in files)
    log(f"website: {os.path.relpath(WEBSITE)}: {len(files)} images, {total / 1e6:.1f} MB; "
        f"stats {stats}")


def _website_main_extras(img_dir, save):
    """The colours gallery's previews, dark and light, with and without the
    accent on the fork: only on the main site."""
    from PIL import Image
    from distributary import options
    opt_dir = os.path.join(img_dir, "options")
    os.makedirs(opt_dir, exist_ok=True)
    for f in os.listdir(opt_dir):   # colours come and go
        os.remove(os.path.join(opt_dir, f))
    previews = [(k, a, b) for k, _, _, a, b in options.colours()]
    previews += [(k + options.EVEN, a, b) for k, _, a, b in options.even_variants()]
    for name, dark_pal, light_pal in previews:
        for which, pal in (("dark", dark_pal), ("light", light_pal)):
            d = options.design_for(pal)
            r = render.render(View(W=1280, H=720), d, logo=logo_for(1280, 720, d))
            im = Image.fromarray(encode.dither_quantize(r["sdr"], 8))
            im.save(os.path.join(opt_dir, f"{name}-{which}.jpg"), quality=88, optimize=True,
                    progressive=True, subsampling=0)

    link = os.path.join(WEBSITE, "media")
    if not os.path.lexists(link):
        os.symlink("../media", link)


# wallpaper sizes offered for download: common screens, 16:9, 16:10,
# ultrawide and phones; each comes from the render of its shape
DOWNLOAD_SIZES = [
    (1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (3200, 1800),
    (3840, 2160), (4480, 2520), (5120, 2880), (6016, 3384), (7680, 4320),
    (1280, 800), (1440, 900), (1680, 1050), (1920, 1200), (2160, 1350), (2560, 1600),
    (2880, 1800), (2944, 1840), (3072, 1920), (3840, 2400),
    (2160, 1440), (2256, 1504), (2304, 1536), (2880, 1920), (3000, 2000),
    (2560, 1664), (2880, 1864), (3024, 1964), (3456, 2234),
    (1024, 768), (1600, 1200), (2048, 1536), (2732, 2048), (1280, 1024), (2560, 2048),
    (2560, 1080), (3440, 1440), (3840, 1600), (5120, 2160), (3840, 1080), (5120, 1440),
    (1080, 2340), (1170, 2532), (1290, 2796), (1440, 3120), (1080, 2400), (1440, 3200),
    (1080, 2160), (1440, 2880), (2160, 4320)]

# how the download picker and the palette editor group those sizes, in order
SHAPES = [("16:9", 16 / 9), ("16:10", 1.6), ("3:2", 1.5), ("MacBook", 2560 / 1664),
          ("4:3", 4 / 3), ("5:4", 1.25), ("Ultrawide", 2.4), ("Super ultrawide (32:9)", 32 / 9),
          ("Phone (19.5:9)", 9 / 19.5), ("Phone (20:9)", 0.45), ("Phone (2:1)", 0.5)]


def size_groups(sizes=DOWNLOAD_SIZES):
    """[[label, [[W, H], ...]], ...]: sizes by screen shape, narrowest first."""
    def shape(W, H):
        r = W / H
        if 2.2 < r < 2.6:              # 21:9 comes in several widths
            return "Ultrawide"
        return min(SHAPES, key=lambda sh: abs(sh[1] - r))[0]
    groups = {label: [] for label, _ in SHAPES}
    for W, H in sizes:
        groups[shape(W, H)].append([W, H])
    return [[label, sorted(groups[label])] for label, _ in SHAPES if groups[label]]


def build_downloads():
    """Wallpapers to download, into build/downloads/<option>/: a JPEG per
    size, dark and light (from the native render of that shape, or scaled
    down from the nearest larger one), the HDR gain-map AVIFs where there is
    light brighter than white, and the SVGs."""
    from PIL import Image
    key = DOWNLOAD_KEY
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "downloads", key)
    shutil.rmtree(d, ignore_errors=True)        # sizes and files come and go
    os.makedirs(d)
    wp = os.path.join(OUT, "wallpapers")
    made = 0
    for mode in ("dark", "light"):
        renders = {}
        for f in os.listdir(wp):
            m = re.match(rf"{THEME}-{mode}-(\d+)x(\d+)\.png$", f)
            if m:
                renders[(int(m.group(1)), int(m.group(2)))] = os.path.join(wp, f)
        for W, H in DOWNLOAD_SIZES:
            same = [s for s in renders if abs(s[0] / s[1] - W / H) < 0.003 and s[0] >= W]
            if not same:
                log(f"downloads: no render for {W}x{H}")
                continue
            src = min(same, key=lambda s: s[0])
            im = Image.open(renders[src]).convert("RGB")
            if src != (W, H):
                im = im.resize((W, H), Image.LANCZOS)
            im.save(os.path.join(d, f"{THEME}-{key}-{mode}-{W}x{H}.jpg"), quality=92,
                    optimize=True, progressive=True, subsampling=0)
            made += 1
        svg = os.path.join(OUT, f"{THEME}-theme", "wallpaper" if mode == "dark" else "wallpaper-light",
                           "contents", "images", "1920x1080.svg")
        shutil.copy(svg, os.path.join(d, f"{THEME}-{key}-{mode}.svg"))
    for f in sorted(os.listdir(os.path.join(OUT, "hdr"))):
        m = re.match(rf"{THEME}-dark-(\d+x\d+)-gainmap\.avif$", f)
        if not m:
            continue
        # nothing brighter than white (Lineage, or no accent on the fork): no HDR file to offer
        with open(os.path.join(OUT, "hdr", f"{THEME}-dark-{m.group(1)}-hdr.json")) as fh:
            if json.load(fh)["MaxCLL"] <= encode.REFERENCE_WHITE_NITS:
                continue
        shutil.copy(os.path.join(OUT, "hdr", f), os.path.join(d, f"{THEME}-{key}-dark-{m.group(1)}-hdr.avif"))
    total = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
    log(f"downloads: {os.path.relpath(d)}  {made} JPEGs + SVGs + HDR, {total / 1e6:.0f} MB")


def build_switcher():
    """website/schemes/index.js: what the main page needs to show itself in
    each colour whose pictures are built (./build.py --scheme KEY --draft all
    website), with and without the accent on the fork: its words, pictures,
    thumbnails, downloads, HDR figures, legend and page colours."""
    from PIL import Image
    from distributary import options
    from distributary.raster import hex_lin
    root = os.path.dirname(os.path.abspath(__file__))

    def hx(rgb):
        return "#" + "".join(f"{int(round(min(1, max(0, c)) * 255)):02x}" for c in rgb)

    def rgb(h):
        return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]

    def mix(a, b, t):
        return hx([x + (y - x) * t for x, y in zip(rgb(a), rgb(b))])

    def lum(h):
        return float(np.dot(hex_lin(h), [0.2126, 0.7152, 0.0722]))

    def contrast(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)

    def readable(fg, bg, toward):
        """fg moved toward white or black until it reads on bg (WCAG AA)."""
        for t in np.linspace(0, 1, 41):
            c = mix(fg, toward, t)
            if contrast(c, bg) >= 4.6:
                return c
        return toward

    def listing(d):
        return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))) if os.path.isdir(d) else []

    def version(name, img, media):
        """One version of a colour: the pictures and videos it has (the page
        shows the lit version's in place of missing ones), its gallery previews
        and the switcher's thumbnails of them, its downloads and HDR figures."""
        v = {"images": listing(img), "media": listing(media), "previews": {}, "thumbs": {}}
        for mode in ("dark", "light"):
            src = os.path.join(WEBSITE, "img", "options", f"{name}-{mode}.jpg")
            if os.path.exists(src):
                v["previews"][mode] = f"img/options/{name}-{mode}.jpg"
                v["thumbs"][mode] = f"schemes/thumbs/{name}-{mode}.jpg"
                Image.open(src).convert("RGB").resize((320, 180), Image.LANCZOS).save(
                    os.path.join(WEBSITE, v["thumbs"][mode]), quality=84, optimize=True, progressive=True)
        # what can be downloaded (./build.py [--scheme NAME] downloads)
        dl = os.path.join(root, "build", "downloads", name)
        v["downloads"] = ({f: os.path.getsize(os.path.join(dl, f)) for f in sorted(os.listdir(dl))}
                          if os.path.isdir(dl) else {})
        if os.path.exists(os.path.join(img, "hdr-stats.json")):
            with open(os.path.join(img, "hdr-stats.json")) as f:
                v["stats"] = json.load(f)
        return v

    thumbs_dir = os.path.join(WEBSITE, "schemes", "thumbs")
    shutil.rmtree(thumbs_dir, ignore_errors=True)     # colours come and go
    os.makedirs(thumbs_dir)
    def legend(dark, light, names):
        """[colour, name] for the fork, mid-river and the spreading delta,
        dark and light: the accent at the fork is a light on the dark ground
        and the deepest ink on the paper; a colour from the source (Lineage's
        red) covers the fork instead.  names: {mode: [three names]}, or two
        names (source, spreading) for an even palette."""
        out = {}
        for mode, pal in (("dark", dark), ("light", light)):
            near = lambda d: min(pal.water, key=lambda st: abs(st[0] - d))[1]
            first = pal.source_tint[0] if pal.source_tint else pal.water[0][1]
            picks = [first, near(0.65), near(1.6)] if len(names[mode]) == 3 else [first, near(1.6)]
            out[mode] = [[c, n] for c, n in zip(picks, names[mode])]
        return out

    even = {k: (a, b) for k, _, a, b in options.even_variants()}
    out = {}
    for key, title, change, dark, light in options.colours():
        here = WEBSITE if key == MAIN else os.path.join(WEBSITE, "schemes", key)
        img = os.path.join(here, "img")
        if key != MAIN and not os.path.exists(os.path.join(img, "hdr-stats.json")):
            continue
        entry = {"title": title, "change": change, **version(key, img, os.path.join(here, "media"))}
        g = dark.land[1][1]
        paper, ink = light.land[1][1], light.logo_colour
        tokens = {
            "dark": {"--ground": g, "--raised": mix(g, "#ffffff", 0.05), "--ink": mix(g, "#ffffff", 0.92),
                     "--muted": readable(mix(g, "#ffffff", 0.6), g, "#ffffff"),
                     "--line": "rgba(255, 255, 255, 0.12)",
                     "--accent": readable(dark.water[3][1], g, "#ffffff"),
                     "--light": readable(dark.water[1][1], g, "#ffffff"),
                     "--code-bg": mix(g, "#ffffff", 0.03)},
            "light": {"--ground": paper, "--raised": mix(paper, "#000000", 0.04), "--ink": ink,
                      "--muted": readable(mix(ink, paper, 0.35), paper, "#000000"),
                      "--line": "rgba(0, 0, 0, 0.14)",
                      "--accent": readable(light.water[1][1], paper, "#000000"),
                      "--light": readable(light.water[0][1], paper, "#000000"),
                      "--code-bg": mix(paper, "#000000", 0.03)},
        }
        if key != PAGE_OWN:             # it keeps the page's own, hand-set colours
            entry["tokens"] = tokens
        if dark.source_tint:
            names = {m: ["From the source through the first forks", "Mid-river", "As the delta spreads"]
                     for m in ("dark", "light")}
        elif key == PAGE_OWN:           # the page's own words for its own colours
            names = {"dark": ["Light at the first fork", "Rose", "Violet, as the delta spreads"],
                     "light": ["Deepest ink at the first fork", "Rose", "Violet, as the delta spreads"]}
        else:
            names = {"dark": ["Light at the first fork", "Mid-river", "As the delta spreads"],
                     "light": ["Deepest ink at the first fork", "Mid-river", "As the delta spreads"]}
        entry["legend"] = legend(dark, light, names)
        if key in even:
            name = key + options.EVEN
            there = os.path.join(WEBSITE, "schemes", name)
            entry["even"] = {**version(name, os.path.join(there, "img"), os.path.join(there, "media")),
                             "legend": legend(*even[key], {m: ["From the source through the first forks",
                                                               "As the delta spreads"] for m in ("dark", "light")})}
        out[key] = entry
    path = os.path.join(WEBSITE, "schemes", "index.js")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("// generated by ./build.py switcher: the colours the page can show\n")
        f.write("window.DISTRIBUTARY_SCHEMES = " + json.dumps(out, indent=1) + ";\n")
        f.write("// the download sizes by screen shape, as the palette editor lists them\n")
        f.write("window.DISTRIBUTARY_SIZES = " + json.dumps(size_groups()) + ";\n")
    log(f"switcher: {os.path.relpath(path)}  {', '.join(out)}")


def build_editor():
    """Data for the palette editor (website/editor/, hand-written page).

    The editor redraws the picture in the browser with WebGL, from the same
    formulas as scene.py and svgout.py.  Only colour and light change there,
    so the river is exported once as geometry: channels (centre line, width,
    distance from the source), fork joints and bank contours, as far as any
    screen size it offers (the download sizes, framed by view_for) can see.
    The colour options come along as presets.
    """
    from distributary import logo as debian_logo
    from distributary import options
    from distributary.contours import _rdp
    des = D.get("dark")
    boxes = [world_box(view_for(W, H)) for W, H in DOWNLOAD_SIZES]
    x0, x1 = min(b[0] for b in boxes), max(b[1] for b in boxes)
    y0, y1 = min(b[2] for b in boxes), max(b[3] for b in boxes)
    m = 0.06

    def inside(x, y):
        return (x > x0 - m) & (x < x1 + m) & (y > y0 - m) & (y < y1 + m)

    def flat(*cols, nd=(4,)):
        out = []
        for row in zip(*cols):
            out += [round(float(v), n) for v, n in zip(row, nd)]
        return out

    channels, discs = [], []
    for b in sorted(des.branches, key=lambda b: b["width"]):
        idx = np.flatnonzero(inside(b["x"], b["y"]))
        if len(idx) == 0:
            continue
        i0, i1 = max(0, idx[0] - 1), min(len(b["x"]) - 1, idx[-1] + 1)
        keep = np.unique(np.r_[np.arange(i0, i1 + 1, 2), i1])     # every other point
        s_abs = des.offsets[b["id"]] + b["s"][keep]
        ease = np.clip(b["s"][keep] / max(6.0 * b["birth_width"], 1e-6), 0, 1)
        channels.append({"birth": round(float(b["birth_width"]), 6),
                         "width": round(float(b["width"]), 6),
                         "p": flat(b["x"][keep], b["y"][keep], b["w"][keep], s_abs, ease,
                                   nd=(4, 4, 6, 4, 3))})
        if b["parent"] >= 0 and inside(np.array([b["fx"]]), np.array([b["fy"]]))[0]:
            discs.append({"x": round(float(b["fx"]), 4), "y": round(float(b["fy"]), 4),
                          "w": round(float(b["birth_width"]), 6),
                          "s": round(float(des.offsets[b["id"]]), 4)})
    contours = []
    for k, pts in des.contours:
        ok = inside(pts[:, 0], pts[:, 1])
        # split into runs inside the frame, then simplify well below a pixel
        for run in np.split(np.arange(len(pts)), np.flatnonzero(np.diff(ok.astype(int))) + 1):
            if not ok[run[0]] or len(run) < 2:
                continue
            q = _rdp(pts[run], 0.00015)
            contours.append({"k": int(k), "p": flat(q[:, 0], q[:, 1], nd=(4, 4))})

    # the lockup in a 1080-high frame: bottom left on 16:9 (the editor moves
    # it to other shapes' place with LOGO_X), and centred on x = 0 for
    # portraits (the editor moves it to the middle of the screen) at
    # --logo-scale 1; the editor scales it about (x, y) with its own slider
    lg = logo_for(1920, 1080, des, scale=1.0)
    lg.update(colour="currentColor", opacity=1.0)
    frag, _ = debian_logo.lockup(**lg)
    logo_at = [lg["x"], lg["y"]]
    lg = logo_for(540, 1080, des, scale=1.0)
    lg.update(x=0, colour="currentColor", opacity=1.0)
    frag_portrait, _ = debian_logo.lockup(**lg)
    logo_portrait_y = lg["y"]
    fork, near, far = options.fork_distances()
    presets = [{"key": k, "title": t, "change": c,
                "dark": D.palette_to_json(a), "light": D.palette_to_json(b)}
               for k, t, c, a, b in options.schemes() + options.departures()]
    data = {"seed": D.NETWORK.seed, "root_width": des.root_width,
            "frame": {"height": view_for(1920, 1080).height, "portrait_height": PORTRAIT_HEIGHT,
                      "delta_reach": DELTA_REACH, "logo_height_px": 1080},
            "sizes": size_groups(),
            "forks": {"first": round(fork, 4), "next": [round(near, 4), round(far, 4)]},
            "channels": channels, "discs": discs, "contours": contours,
            "logo": frag, "logo_portrait": frag_portrait,
            "logo_at": logo_at, "logo_x": LOGO_X, "logo_portrait_y": logo_portrait_y,
            "presets": presets}
    d = os.path.join(EDITOR, "data")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "river.js")
    with open(path, "w") as f:
        f.write("// generated by ./build.py editor: the river (seed "
                f"{D.NETWORK.seed}), colour presets and logo for the palette editor\n")
        f.write("window.DISTRIBUTARY = " + json.dumps(data, separators=(",", ":")) + ";\n")
    npts = sum(len(c["p"]) // 5 for c in channels)
    log(f"editor: {os.path.relpath(path)}  {len(channels)} channels ({npts} points), "
        f"{len(discs)} forks, {len(contours)} contour runs, {len(presets)} presets, "
        f"{os.path.getsize(path) / 1024:.0f} KiB")


TARGETS = {
    "svg": build_svg,
    "raster": build_raster,
    "hdr": build_hdr,
    "grub": build_grub,
    "plymouth": build_plymouth,
    "installer": build_installer,
    "banners": build_banners,
    "previews": build_previews,
    "video": build_video,
    "website": build_website,
    "editor": build_editor,
    "switcher": build_switcher,
    "downloads": build_downloads,
}
SLOW = {"video", "website", "editor", "switcher", "downloads"}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", default=["all"])
    ap.add_argument("--scheme", metavar="NAME",
                    help="build a colour option from src/distributary/options.py into "
                         "build/schemes/NAME, its showcase pictures into website/schemes/NAME")
    ap.add_argument("--palette", metavar="FILE",
                    help="build a palette saved from the palette editor (JSON), "
                         "like --scheme")
    ap.add_argument("--seed", type=int, metavar="N",
                    help="grow another river (the proposal, its previews and the editor "
                         f"use seed {D.NETWORK.seed}); outputs get their own directories")
    ap.add_argument("--logo-scale", type=float, metavar="K",
                    help="the Debian logo and wordmark K times their size on the wallpapers "
                         "and the login screen (default 1, or the palette's logo_scale)")
    ap.add_argument("--draft", action="store_true",
                    help="4K at most: skip the 5K and 8K renders and the videos")
    args = ap.parse_args()
    global OUT, TITLE, WEBSITE, EDITOR, SCHEME, DRAFT, RASTER_SIZES, HDR_SIZES, DOWNLOAD_KEY, LOGO_SCALE
    root = os.path.dirname(os.path.abspath(__file__))
    if args.scheme and args.palette:
        ap.error("--scheme and --palette both choose the colours; give one")
    targets = []
    for t in args.targets:          # "all" expands in place: "all website" runs both
        targets += [k for k in TARGETS if k not in SLOW] if t == "all" else [t]
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        ap.error(f"unknown target {unknown[0]!r}; choose from {', '.join(TARGETS)}, all")
    if args.seed is not None:
        D.NETWORK.seed = args.seed          # before anything grows the river
        D.get.cache_clear()
    if args.scheme or args.palette:
        from distributary import options
        if args.scheme:
            try:
                title, dark, light = options.scheme(args.scheme)
            except KeyError as e:
                ap.error(str(e.args[0]))
            key = args.scheme
        else:
            title, dark, light, key, seed, logo_scale = _read_palette(ap, args.palette)
            LOGO_SCALE = logo_scale
            if seed is not None and seed != D.NETWORK.seed:
                log(f"note: {args.palette} was made on seed {seed}; building on seed "
                    f"{D.NETWORK.seed} (use --seed {seed} for that river)")
        D.use(dark, light)
        SCHEME, TITLE = key, f"{TITLE} {title}"
        OUT = os.path.join(root, "build", "schemes", key)
        # a colour option's pictures live inside the main site, which can
        # switch to them; an editor palette gets a site of its own
        WEBSITE = (os.path.join(root, "website", "schemes", key) if args.scheme
                   else os.path.join(root, "sites", key))
        if args.scheme and args.scheme.endswith(options.EVEN):
            # nothing in it is brighter than white: the site's luminance map
            # needs one HDR master, and there are no HDR files to offer
            HDR_SIZES = [(3840, 2160)]
    chosen = SCHEME                     # the colours asked for, if any, before --seed names a build
    if args.seed is not None:
        tag = f"seed{args.seed}"
        OUT = os.path.join(OUT, tag) if SCHEME else os.path.join(root, "build", tag)
        WEBSITE = os.path.join(root, "sites", f"{SCHEME}-{tag}" if SCHEME else tag)
        EDITOR = os.path.join(root, "sites", f"editor-{tag}", "editor")
        SCHEME = SCHEME or tag              # its site has no videos or README pictures
    DOWNLOAD_KEY = (chosen or MAIN) + (f"-seed{args.seed}" if args.seed is not None else "")
    if args.logo_scale is not None:     # over the palette's own
        if not 0 < args.logo_scale <= 4:
            ap.error("--logo-scale takes a number above 0, up to 4")
        LOGO_SCALE = args.logo_scale
    if LOGO_SCALE != 1:
        log(f"the Debian logo at {LOGO_SCALE:g} times its size")
    if args.draft:
        DRAFT = True
        RASTER_SIZES = [s for s in RASTER_SIZES if max(s) <= 3840]
        HDR_SIZES = [s for s in HDR_SIZES if max(s) <= 3840]
    for t in targets:
        TARGETS[t]()


def _read_palette(ap, path):
    """(title, dark, light, key, seed, logo_scale) from a palette saved by the editor.

    Its key names its build directory; it never takes the name of a colour
    option or of its even version, so it cannot overwrite their files."""
    from distributary import options
    try:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, ValueError) as e:
        ap.error(f"cannot read the palette {path}: {e}")
    if isinstance(spec, dict):
        # palettes saved before the two versions were called dark and light
        for mode, old in (("dark", "dusk"), ("light", "dawn")):
            if mode not in spec and old in spec:
                spec[mode] = spec.pop(old)
    if not isinstance(spec, dict) or not all(isinstance(spec.get(m), dict) for m in ("dark", "light")):
        ap.error(f"{path} is not a palette: it needs \"dark\" and \"light\" objects, "
                 "as the palette editor writes them")
    key = re.sub(r"[^a-z0-9]+", "-", str(spec.get("name") or
                                        os.path.splitext(os.path.basename(path))[0]).lower()).strip("-")
    taken = {name for k, *_ in options.colours() for name in (k, k + options.EVEN)}
    if not key or key in taken:
        key = "palette-" + (key or "unnamed")
    palettes = []
    for mode in ("dark", "light"):
        known = {f.name for f in dataclasses.fields(D.Palette)} - {"name"}
        extra = sorted(set(spec[mode]) - known - {"text_colour"})   # dropped field
        if extra:
            log(f"note: {path}: ignoring unknown {mode} fields: {', '.join(extra)}")
        try:
            palettes.append(D.palette_from_json(spec[mode], mode))
        except TypeError as e:
            ap.error(f"{path}: the {mode} palette is incomplete ({e})")
    seed = spec.get("seed")
    scale = spec.get("logo_scale", 1.0)
    if not isinstance(scale, (int, float)) or isinstance(scale, bool) or not 0 < scale <= 4:
        ap.error(f"{path}: logo_scale must be a number above 0, up to 4")
    return (str(spec.get("title") or key), palettes[0], palettes[1], key,
            seed if isinstance(seed, int) else None, float(scale))


if __name__ == "__main__":
    main()
