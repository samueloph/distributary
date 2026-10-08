# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Compositing: float base (numpy) + vector overlay (librsvg) -> SDR, HDR."""

import cairo
import gi
import numpy as np

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402

from . import scene, svgout  # noqa: E402
from .raster import linear_to_srgb, srgb_to_linear, tonemap_sdr  # noqa: E402


def draw_svg_over(rgb, svg_text):
    """Render an SVG over an sRGB float image with librsvg, in float."""
    H, W = rgb.shape[:2]
    surf = cairo.ImageSurface(cairo.Format.RGBA128F, W, H)
    stride = surf.get_stride() // 16
    buf = np.ndarray((H, stride, 4), dtype=np.float32, buffer=surf.get_data())
    buf[:, :W, :3] = rgb
    buf[:, :W, 3] = 1.0
    surf.mark_dirty()
    ctx = cairo.Context(surf)
    handle = Rsvg.Handle.new_from_data(svg_text.encode())
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    handle.render_document(ctx, vp)
    surf.flush()
    return np.array(buf[:, :W, :3])


def render(view, design, logo=None, hdr=False, scrim=None):
    """Return dict(sdr=sRGB float image[, hdr=linear image, 1.0 = SDR white])."""
    knee = design.palette.knee
    base_lin, scene_lin = scene.layers(view, design)
    base = linear_to_srgb(tonemap_sdr(base_lin, knee=knee)).astype(np.float32)
    doc = svgout.document(view, design, logo=logo, scrim=scrim)
    sdr = np.clip(draw_svg_over(base, doc), 0, 1)
    out = {"sdr": sdr}
    if hdr:
        # HDR = the SDR picture plus exactly the light the tone curve removed
        resid = np.maximum(scene_lin - tonemap_sdr(scene_lin, knee=knee), 0)
        out["hdr"] = srgb_to_linear(sdr).astype(np.float32) + resid
    return out
