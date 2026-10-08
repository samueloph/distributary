# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""SVG writer: the vector half of every output.

The same document drives both deliverables: saved with an embedded base
image it is the desktop-base SVG; rendered by librsvg over a full-resolution
float base it becomes the PNG/HDR renders.  So they cannot drift apart.
"""

import base64
from xml.sax.saxutils import escape as xml_escape

import numpy as np

from . import logo as debian_logo
from .geometry import ribbon
from .raster import linear_to_srgb, tonemap_sdr
from .scene import ramp, shade, tinted

GRADIENT_STOPS = 20


def _hex(rgb):
    r, g, b = (int(round(float(c) * 255)) for c in np.clip(rgb, 0, 1))
    return f"#{r:02x}{g:02x}{b:02x}"


def _num(v):
    s = f"{v:.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _poly(X, Y, closed):
    pts = " ".join(f"{_num(x)} {_num(y)}" for x, y in zip(X, Y))
    return f"M{pts}{'Z' if closed else ''}"


def _simplify(X, Y, tol):
    from .contours import _rdp
    pts = _rdp(np.column_stack([X, Y]), tol)
    return pts[:, 0], pts[:, 1]


def _gradient(gid, view, pal, value, tint=0.0):
    """Elliptical radial gradient reproducing the water radiance field."""
    gx, gy = pal.glint
    rx, ry = pal.glint_r
    ox, oy = view.to_px(gx, gy)
    ax, ay = view.to_px(gx + rx, gy)
    bx, by = view.to_px(gx, gy + ry)
    dmax = pal.water[-1][0]
    ds = np.linspace(0, dmax, GRADIENT_STOPS)
    cols = linear_to_srgb(tonemap_sdr(shade(tinted(ramp(ds, pal.water), tint, pal), value, pal),
                                      knee=pal.knee))
    stops = "".join(f'<stop offset="{d / dmax:.4f}" stop-color="{_hex(c)}"/>'
                    for d, c in zip(ds, cols))
    m = (f"matrix({ax - ox:.4f} {ay - oy:.4f} {bx - ox:.4f} {by - oy:.4f} "
         f"{ox:.3f} {oy:.3f})")
    return (f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" cx="0" cy="0" '
            f'r="{dmax}" gradientTransform="{m}">{stops}</radialGradient>')


def _in_view(X, Y, view, margin=40):
    return not (X.max() < -margin or X.min() > view.W + margin or
                Y.max() < -margin or Y.min() > view.H + margin)


ALL_PARTS = frozenset({"contours", "channels", "logo"})


def document(view, design, base_png=None, logo=None,
             title="Distributary", simplify_px=0.12, corner_radius=0,
             parts=ALL_PARTS, scrim=None):
    """Build the SVG.  `logo`: None or dict(x, y, height, ...) in pixels.

    `parts` selects the vector layers to emit (the motion renderer draws
    single layers as overlays).
    """
    pal = design.palette
    W, H = view.W, view.H
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
           f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f"<title>{xml_escape(title)}</title>", _METADATA, "<defs>"]
    if corner_radius:
        out.append(f'<clipPath id="rounded"><rect width="{W}" height="{H}" '
                   f'rx="{corner_radius}" ry="{corner_radius}"/></clipPath>')

    # channels grouped by their (quantised) light value
    groups, discs = {}, {}
    for pc in design.pieces:
        v = (pc["value"], pc.get("tint", 0.0))
        px, py = ribbon(pc["x"], pc["y"], pc["w"])
        X, Y = view.to_px(px, py)
        if not _in_view(X, Y, view):
            continue
        X, Y = _simplify(X, Y, simplify_px)
        groups.setdefault(v, []).append(_poly(X, Y, True))
    for f in design.forks:
        cx, cy = view.to_px(f["x"], f["y"])
        if -40 < cx < view.W + 40 and -40 < cy < view.H + 40:
            discs.setdefault((f["value"], f["tint"]), []).append(
                (cx, cy, 0.5 * f["width"] * view.scale))
    levels = sorted(set(groups) | set(discs) | {(1.0, 0.0)})
    ids = {}
    for i, (v, t) in enumerate(levels):
        ids[(v, t)] = f"water{i}"
        out.append(_gradient(ids[(v, t)], view, pal, v, t))
    out.append("</defs>")
    if corner_radius:
        out.append('<g clip-path="url(#rounded)">')

    if base_png is not None:
        b64 = base64.b64encode(base_png).decode()
        out.append(f'<image id="base" x="0" y="0" width="{W}" height="{H}" '
                   f'preserveAspectRatio="none" xlink:href="data:image/png;base64,{b64}"/>')

    if "contours" in parts:
        # bank contours: faint lines coloured by the same water light
        spacing, rings, gain, lw = pal.contours
        out.append(f'<g id="contours" fill="none" stroke="url(#{ids[(1.0, 0.0)]})" '
                   f'stroke-width="{_num(lw * view.scale)}" stroke-linejoin="round" '
                   f'stroke-linecap="round">')
        by_ring = {}
        for k, pts in design.contours:
            X, Y = view.to_px(pts[:, 0], pts[:, 1])
            if not _in_view(X, Y, view):
                continue
            X, Y = _simplify(X, Y, simplify_px)
            by_ring.setdefault(k, []).append(_poly(X, Y, False))
        for k in sorted(by_ring):
            out.append(f'<path stroke-opacity="{design.ring_alpha(k):.4f}" '
                       f'd="{"".join(by_ring[k])}"/>')
        out.append("</g>")

    if "channels" in parts:
        # the river itself; thinner (dimmer) channels first.  One group opacity,
        # so overlapping pieces never double up at the forks.
        out.append(f'<g id="channels" opacity="{pal.channel_opacity:.3f}">')
        for v in levels:
            if v in groups:
                out.append(f'<path fill="url(#{ids[v]})" d="{"".join(groups[v])}"/>')
            for cx, cy, r in discs.get(v, []):
                out.append(f'<circle cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}" '
                           f'fill="url(#{ids[v]})"/>')
        out.append("</g>")

    if scrim:
        # land colour fading out behind text that sits over the picture:
        # (x where it is fully on, x where it has faded out, opacity) in px
        x_on, x_off, alpha = scrim
        col = _hex(linear_to_srgb(ramp([0.0], pal.land)[0]))
        out.append(f'<defs><linearGradient id="scrim" gradientUnits="userSpaceOnUse" '
                   f'x1="{_num(x_on)}" y1="0" x2="{_num(x_off)}" y2="0">'
                   f'<stop offset="0" stop-color="{col}" stop-opacity="{alpha:.3f}"/>'
                   f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>'
                   f'<rect width="{W}" height="{H}" fill="url(#scrim)"/>')
    if logo and "logo" in parts:
        frag, _ = debian_logo.lockup(**logo)
        out.append(f'<g id="logo">{frag}</g>')
    if corner_radius:
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


_METADATA = """<metadata>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:cc="http://creativecommons.org/ns#" xmlns:dc="http://purl.org/dc/elements/1.1/">
<cc:Work rdf:about=""><dc:title>Distributary — Debian 14 "forky" artwork</dc:title>
<dc:description>Generated by the Distributary program, https://salsa.debian.org/samueloph/distributary</dc:description>
<dc:rights>GPL-2.0-or-later OR CC-BY-SA-4.0; Debian Open Use Logo: LGPL-3.0-or-later OR CC-BY-SA-3.0</dc:rights>
<cc:license rdf:resource="https://www.gnu.org/licenses/old-licenses/gpl-2.0.html"/>
<cc:license rdf:resource="http://creativecommons.org/licenses/by-sa/4.0/"/></cc:Work>
</rdf:RDF></metadata>"""
