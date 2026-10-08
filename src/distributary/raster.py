# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Scene-linear raster renderer.

Everything is computed in linear light (Rec.709 primaries) where 1.0 is SDR
reference white (203 cd/m2 in the HDR encodings).  The SDR outputs are a
tone-mapped view of the same scene; the HDR outputs keep the highlights.
"""

import math

import cairo
import numpy as np
from scipy import ndimage

from .geometry import ribbon


# -- colour helpers ----------------------------------------------------------

def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0.0, None)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hex_lin(h):
    h = h.lstrip("#")
    return srgb_to_linear([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


LUMA = np.array([0.2126, 0.7152, 0.0722])


# -- pixel grid in world coordinates -------------------------------------------

def world_grid(view, step=1):
    """World coordinates of pixel centres, shape (H, W) each."""
    px = (np.arange(0, view.W, step) + 0.5)
    py = (np.arange(0, view.H, step) + 0.5)
    PX, PY = np.meshgrid(px, py)
    x = PX / view.scale + (view.cx - view.width / 2)
    y = PY / view.scale + (view.cy - view.height / 2)
    if view.rotate == 90:                     # inverse of to_px rotation
        x, y = y, -x
    return x, y


# -- rasterisation -----------------------------------------------------------

def rasterize(branches, view, value_fn, width_scale=1.0, order_key=None, discs=()):
    """Fill ribbons into a float map.

    value_fn(piece) -> scalar painted for that channel (opaque OVER, so the
    last-painted channel wins where they overlap); `discs` are round fork
    joints (dicts with x, y, width and whatever value_fn reads).  Returns (value, cover) as float32 arrays;
    value is premultiplied by coverage.
    """
    W, H = view.W, view.H
    surf = cairo.ImageSurface(cairo.Format.RGBA128F, W, H)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.Antialias.GOOD)
    ctx.set_fill_rule(cairo.FillRule.WINDING)
    order = sorted(branches, key=order_key or (lambda b: b["width"]))
    for b in order:
        px, py = ribbon(b["x"], b["y"], b["w"] * width_scale)
        X, Y = view.to_px(px, py)
        if X.max() < -50 or X.min() > W + 50 or Y.max() < -50 or Y.min() > H + 50:
            continue
        v = float(value_fn(b))
        ctx.set_source_rgba(v, v, v, 1.0)
        ctx.move_to(X[0], Y[0])
        for xx, yy in zip(X[1:], Y[1:]):
            ctx.line_to(xx, yy)
        ctx.close_path()
        ctx.fill()
    for disc in discs:
        # round joint at a fork, sized and lit like the incoming channel
        jx, jy = view.to_px(disc["x"], disc["y"])
        v = float(value_fn(disc))
        ctx.set_source_rgba(v, v, v, 1.0)
        ctx.arc(float(jx), float(jy), 0.5 * disc["width"] * width_scale * view.scale,
                0, 2 * math.pi)
        ctx.fill()
    surf.flush()
    buf = np.ndarray((H, surf.get_stride() // 16, 4), dtype=np.float32,
                     buffer=surf.get_data())[:, :W, :]
    # cairo float formats are stored as R, G, B, A floats (premultiplied)
    return buf[..., 0].copy(), buf[..., 3].copy()


# -- filtering -----------------------------------------------------------------

def blur(img, sigma):
    """Gaussian blur with a pyramid for large radii (sigma in pixels)."""
    if sigma <= 0:
        return img
    if sigma < 12:
        return _gauss(img, sigma)
    # downsample by 2^k so that the residual sigma is ~6px
    k = int(math.floor(math.log2(sigma / 6.0)))
    f = 2 ** k
    small = _downsample(img, f)
    small = _gauss(small, math.sqrt(max(sigma ** 2 - (0.5 * f) ** 2, 1.0)) / f)
    return _upsample(small, f, img.shape)


def _gauss(img, sigma):
    if img.ndim == 3:
        return np.stack([ndimage.gaussian_filter(img[..., c], sigma, mode="nearest")
                         for c in range(img.shape[2])], axis=-1)
    return ndimage.gaussian_filter(img, sigma, mode="nearest")


def _downsample(img, f):
    H, W = img.shape[:2]
    h, w = H // f, W // f
    cropped = img[:h * f, :w * f]
    shp = (h, f, w, f) + img.shape[2:]
    return cropped.reshape(shp).mean(axis=(1, 3))


def _upsample(small, f, shape):
    H, W = shape[:2]
    h, w = small.shape[:2]
    # map full-res pixel centres into the small grid
    yy = (np.arange(H) + 0.5) / f - 0.5
    xx = (np.arange(W) + 0.5) / f - 0.5
    yy = np.clip(yy, 0, h - 1)
    xx = np.clip(xx, 0, w - 1)
    Y, X = np.meshgrid(yy, xx, indexing="ij")
    if small.ndim == 3:
        return np.stack([ndimage.map_coordinates(small[..., c], [Y, X], order=3,
                                                 mode="nearest")
                         for c in range(small.shape[2])], axis=-1)
    return ndimage.map_coordinates(small, [Y, X], order=3, mode="nearest")


# -- tone mapping ------------------------------------------------------------

def tonemap_sdr(lin, knee=0.62, white=1.0):
    """Hue-preserving highlight roll-off, then desaturate overflow to white.

    Luminance below `knee` passes through untouched, so the SDR image matches
    the HDR one everywhere except in the highlights.  The shoulder is a tanh,
    which joins the identity with matching slope (no kink, no banding).
    """
    L = np.einsum("...c,c->...", lin, LUMA)
    Lc = np.maximum(L, 1e-8)
    span = white - knee
    Lm = np.where(Lc > knee, knee + span * np.tanh((Lc - knee) / span), Lc)
    out = lin * (Lm / Lc)[..., None]
    # a channel still above 1: blend toward the achromatic value just enough
    mx = out.max(axis=-1)
    over = np.clip((mx - 1.0) / np.maximum(mx - Lm, 1e-6), 0, 1)[..., None]
    out = out + (Lm[..., None] - out) * over
    return np.clip(out, 0, 1)
