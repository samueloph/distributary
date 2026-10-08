# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Linear-light layers: land, water radiance, glow, full scene."""

import numpy as np

from . import raster
from .raster import hex_lin, world_grid


def ramp(coord, stops):
    """Piecewise-linear ramp over a scalar field; stops (t, hex[, gain])."""
    ts = np.array([s[0] for s in stops])
    cs = np.array([hex_lin(s[1]) * (s[2] if len(s) > 2 else 1.0) for s in stops])
    out = np.empty(np.shape(coord) + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(coord, ts, cs[:, c])
    return out


def glint_distance(X, Y, pal):
    gx, gy = pal.glint
    rx, ry = pal.glint_r
    return np.hypot((X - gx) / rx, (Y - gy) / ry)


def land(X, Y, pal):
    out = ramp(Y, pal.land)
    gx, gy = pal.glint
    for colour, radius in pal.haze:
        r2 = ((X - gx) ** 2 + (Y - gy) ** 2) / radius ** 2
        out += hex_lin(colour).astype(np.float32) * np.exp(-r2)[..., None]
    return out


def water(X, Y, pal):
    return ramp(glint_distance(X, Y, pal), pal.water)


def tinted(wat, t, pal):
    """Mix the water colour toward palette.source_tint by t (0-1).

    The mix is done on square roots, roughly perceptual: dim red turning
    into bright white water in linear light would take most of its visible
    change in the first few steps of t.
    """
    if not pal.source_tint:
        return wat
    colour, _, _, gain = pal.source_tint
    tc = np.sqrt(hex_lin(colour) * gain).astype(np.float32)
    w = np.sqrt(np.maximum(wat, 0))
    return (w + (tc - w) * t) ** 2


def shade(colour, value, pal):
    """Colour of a channel carrying `value` of the full light."""
    if pal.fade_to is None:
        return colour * value
    paper = hex_lin(pal.fade_to).astype(np.float32)
    return paper + (colour - paper) * value


def layers(view, design):
    """Return (base, scene) in linear light.

    base  = land + glow + soft core light: the smooth raster layer.
    scene = base with the translucent channels over it, i.e. exactly what
            the SVG overlay produces, but without the tone curve (for HDR).
    """
    pal = design.palette
    X, Y = world_grid(view)
    order = lambda p: (p["value"], p.get("tint", 0.0))          # noqa: E731
    val, cov = raster.rasterize(design.pieces, view, lambda p: p["value"],
                                order_key=order, discs=design.forks)
    wat = water(X, Y, pal)
    if pal.source_tint:
        tval, _ = raster.rasterize(design.pieces, view, lambda p: p["tint"],
                                   order_key=order, discs=design.forks)
        t = np.where(cov > 1e-6, tval / np.maximum(cov, 1e-6), 0.0)[..., None]
        wat = tinted(wat, t, pal)
    if pal.fade_to is None:
        emis = wat * val[..., None]
    else:
        v = np.where(cov > 1e-6, val / np.maximum(cov, 1e-6), 1.0)[..., None]
        emis = shade(wat, v, pal) * cov[..., None]
    if pal.glow_mode == "tint":
        # light palettes: stain the land toward the water colour
        g = np.zeros_like(val)
        for sigma, gain in pal.glow:
            g += gain * raster.blur(val, sigma * view.scale)
        g = np.clip(g, 0, 1)[..., None]
        base = land(X, Y, pal) * (1 - g) + wat * g
        a = pal.channel_opacity
        return base, base * (1 - a * cov[..., None]) + a * emis
    glow = np.zeros_like(emis)
    for sigma, gain in pal.glow:
        glow += gain * raster.blur(emis, sigma * view.scale)
    frac, core_blurs = pal.core
    if core_blurs:
        cval, _ = raster.rasterize(design.pieces, view, lambda p: p["value"],
                                   width_scale=frac, order_key=order,
                                   discs=design.forks)
        core = wat * cval[..., None]
        for sigma, gain in core_blurs:
            glow += gain * raster.blur(core, sigma * view.scale)
    base = land(X, Y, pal) + glow
    a = pal.channel_opacity
    scene = base * (1 - a * cov[..., None]) + a * emis
    return base, scene
