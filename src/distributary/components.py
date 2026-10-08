# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Boot and installer artwork: GRUB, Plymouth assets, debian-installer banner."""

import math

import cairo
import numpy as np

from . import render, scene
from . import logo as debian_logo
from .geometry import View
from .raster import hex_lin, linear_to_srgb, srgb_to_linear, tonemap_sdr


def _rgba_surface(W, H):
    return cairo.ImageSurface(cairo.Format.RGBA128F, W, H)


def svg_rgba(svg_text, W, H):
    """Render an SVG on transparency; returns straight (unpremultiplied) RGBA."""
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    surf = _rgba_surface(W, H)
    ctx = cairo.Context(surf)
    h = Rsvg.Handle.new_from_data(svg_text.encode())
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    h.render_document(ctx, vp)
    surf.flush()
    buf = np.ndarray((H, surf.get_stride() // 16, 4), dtype=np.float32,
                     buffer=surf.get_data())[:, :W].copy()
    a = buf[..., 3:4]
    buf[..., :3] = np.where(a > 1e-6, buf[..., :3] / np.maximum(a, 1e-6), 0)
    return buf


def lockup_svg(W, H, height, colour="#ffffff", wordmark=True, descriptor=None):
    frag, width = debian_logo.lockup(0, H / 2, height, colour=colour,
                                     wordmark=wordmark, descriptor=descriptor)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{frag}</svg>'), width


# -- GRUB ------------------------------------------------------------------------

def grub(design, W, H):
    """Dusk, dimmed so GRUB's white menu text stays readable everywhere.

    GRUB draws its menu over the upper two thirds of the screen, so the image
    darkens toward the top and the light at the fork is tamed.
    """
    view = View(W=W, H=H)
    r = render.render(view, design, logo=None)
    lin = srgb_to_linear(r["sdr"])
    y = (np.arange(H) + 0.5) / H
    t = np.clip((y - 0.62) / 0.38, 0, 1)
    dim = 0.26 + 0.34 * t * t * (3 - 2 * t)
    lin = lin * dim[:, None, None]
    return linear_to_srgb(lin)


# -- debian-installer banner -----------------------------------------------------

def installer_banner(design, W=800, H=75, dark=False):
    """d-i banner: a slice of the river, the lockup on the calm left side."""
    # a thin window with the first fork at ~70% of the width, clear of the
    # lockup; the stem runs in from behind it
    view = View(W=W, H=H, cx=-0.88, cy=0.04, height=0.26)
    pal = design.palette
    height = 0.42 * H
    lg = dict(x=0.045 * W, y=H / 2, height=height, colour=pal.logo_colour,
              opacity=0.95, descriptor=debian_logo.DESCRIPTOR)
    r = render.render(view, design, logo=lg, scrim=(0.40 * W, 0.62 * W, 0.92))
    return r["sdr"]


# -- Plymouth ---------------------------------------------------------------------

def progress_frames(design, W=840, H=210, frames=20):
    """RGBA frames of the wallpaper's own river growing, for the boot splash.

    A window onto the real stem, first fork and first branches, feathered
    at its edges; growth follows the distance along the river, hurrying
    through the stem so the forks show by mid-boot.
    """
    from .raster import world_grid
    view = View(W=W, H=H, cx=-0.15, cy=0.04, height=0.45)
    X, Y = world_grid(view)
    pal = design.palette
    land = scene.land(X, Y, pal)
    # distance along the river covered inside the window
    pts, s_all = [], []
    for b in design.branches:
        pts.append(np.column_stack([b["x"], b["y"]]))
        s_all.append(design.offsets[b["id"]] + b["s"])
    pts, s_all = np.concatenate(pts), np.concatenate(s_all)
    px, py = view.to_px(pts[:, 0], pts[:, 1])
    inside = (px > 0) & (px < W) & (py > 0) & (py < H)
    s0, s1 = float(s_all[inside].min()), float(s_all[inside].max())
    # feather the window so channels leaving it fade instead of being cut
    fx = np.clip(np.minimum(np.arange(W) + 0.5, W - np.arange(W) - 0.5) / (0.10 * W), 0, 1)
    fy = np.clip(np.minimum(np.arange(H) + 0.5, H - np.arange(H) - 0.5) / (0.24 * H), 0, 1)
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    feather = (fy[:, None] * fx[None, :])[..., None]
    out = []
    for k in range(frames):
        front = s0 + 0.02 + (s1 - s0) * ((k + 1) / frames) ** 0.7
        _, scene_lin = scene.layers(view, design.grown(front))
        # light over transparency: alpha from the added light itself
        light = np.clip(scene_lin - land, 0, None)
        srgb = linear_to_srgb(tonemap_sdr(light, knee=pal.knee))
        a = np.clip(srgb.max(axis=-1, keepdims=True) * 1.1, 0, 1) * feather
        rgb = np.where(a > 1e-4, srgb / np.maximum(srgb.max(axis=-1, keepdims=True) * 1.1, 1e-4), 0)
        out.append(np.concatenate([np.clip(rgb, 0, 1), a], axis=-1))
    return out


def password_field(W=320, H=44):
    surf = cairo.ImageSurface(cairo.Format.ARGB32, W, H)
    ctx = cairo.Context(surf)
    r = H / 2 - 1
    ctx.new_sub_path()
    ctx.arc(W - 1 - r, H / 2, r, -math.pi / 2, math.pi / 2)
    ctx.arc(1 + r, H / 2, r, math.pi / 2, 3 * math.pi / 2)
    ctx.close_path()
    ctx.set_source_rgba(1, 1, 1, 0.06)
    ctx.fill_preserve()
    ctx.set_source_rgba(1, 1, 1, 0.35)
    ctx.set_line_width(1.5)
    ctx.stroke()
    return surf


def password_dot(D=20, dot=7.0, colour="#ffffff"):
    """One passphrase bullet.

    The script places bullets half an image width apart, so the visible dot
    has to be well under half the canvas to keep a gap between dots.
    """
    surf = cairo.ImageSurface(cairo.Format.ARGB32, D, D)
    ctx = cairo.Context(surf)
    c = linear_to_srgb(hex_lin(colour))
    ctx.set_source_rgba(float(c[0]), float(c[1]), float(c[2]), 1)
    ctx.arc(D / 2, D / 2, dot / 2, 0, 2 * math.pi)
    ctx.fill()
    return surf
