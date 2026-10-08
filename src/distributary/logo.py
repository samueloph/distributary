# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""The Debian open use logo, split into swirl and wordmark.

Source: https://www.debian.org/logos/openlogo.svg
Copyright (c) 1999 Software in the Public Interest, Inc.
LGPL-3+ or CC-BY-SA-3.0 (Debian Open Use Logo license).

Text next to the wordmark (the "14 · FORKY" descriptor on banners, or an
optional "14") is set in Lato (SIL OFL 1.1) and converted to outlines, so
the SVGs never depend on installed fonts.
"""

import functools
import os
import re

ASSETS = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
LOGO = os.path.join(ASSETS, "openlogo.svg")
NUMBER_FONT = "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
# the release, set beside the wordmark on banners
DESCRIPTOR = "14 \u00b7 FORKY"


@functools.lru_cache(maxsize=None)
def _paths():
    s = open(LOGO, encoding="utf-8").read()
    swirl, word = [], []
    for m in re.finditer(r"<path([^>]*)/?>", s, re.S):
        attrs = m.group(1)
        d = " ".join(re.search(r'd="([^"]+)"', attrs, re.S).group(1).split())
        red = 'fill="#A80030"' in attrs
        start_y = float(re.match(r"\s*M\s*-?[\d.]+[, ]\s*(-?[\d.]+)", d).group(1))
        # the swirl sits above y=100 in the source artboard; below is text
        if red and start_y < 100:
            swirl.append(d)
        else:
            word.append((d, red))        # red = the diamond dot of the "i"
    return swirl, word


@functools.lru_cache(maxsize=None)
def _bbox(kind):
    """Ink bounding box (x, y, w, h) of a logo part, measured by librsvg."""
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    body = _group(kind, "#000", "#000")
    doc = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" '
           f'viewBox="0 0 200 200">{body}</svg>')
    h = Rsvg.Handle.new_from_data(doc.encode())
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, 200, 200
    ok, ink, _ = h.get_geometry_for_layer(None, vp)
    return ink.x, ink.y, ink.width, ink.height


def _number_path(text="14"):
    """Outline of `text` in NUMBER_FONT as SVG path data (font units, y up)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    font = TTFont(NUMBER_FONT)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    pen = SVGPathPen(gs)
    x = 0
    for ch in text:
        g = cmap[ord(ch)]
        # flip y and scale so that 1 unit = 1/upm em, baseline at y=0
        gs[g].draw(TransformPen(pen, (1 / upm, 0, 0, -1 / upm, x, 0)))
        x += gs[g].width / upm
    return pen.getCommands(), x


def _group(kind, colour, dot_colour):
    swirl, word = _paths()
    if kind == "swirl":
        return "".join(f'<path d="{d}" fill="{colour}"/>' for d in swirl)
    return "".join(f'<path d="{d}" fill="{dot_colour if red else colour}"/>'
                   for d, red in word)


def _text_path(text, tracking=0.0):
    """Outline of `text` in NUMBER_FONT, 1 unit = 1 em, with letter-spacing."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    font = TTFont(NUMBER_FONT)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    pen = SVGPathPen(gs)
    x = 0.0
    for i, ch in enumerate(text):
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (1 / upm, 0, 0, -1 / upm, x, 0)))
        x += gs[g].width / upm + (tracking if i < len(text) - 1 else 0)
    return pen.getCommands(), x


def lockup(x, y, height, colour="#ffffff", opacity=1.0, wordmark=True,
           number=False, number_colour=None, dot_colour=None, anchor="left",
           descriptor=None, descriptor_colour=None):
    """SVG group: swirl [+ 'debian' [+ descriptor]], swirl `height` px tall.

    The descriptor (e.g. "14 · FORKY") is set in tracked capitals, clearly
    secondary to the wordmark instead of imitating its letterforms.
    (x, y) is the left (or centre, with anchor="middle") of the swirl's
    vertical middle.  Returns (svg_fragment, total_width).
    """
    sx, sy, sw, sh = _bbox("swirl")
    s = height / sh
    parts = []
    width = sw * s
    parts.append((0.0, sy, sx, s, "swirl"))
    if wordmark:
        wx, wy, ww, wh = _bbox("word")
        # wordmark ascender height matches the swirl's height (stock lockup)
        ws = height * 0.95 / wh
        gap = 0.50 * height
        parts.append((width + gap, wy, wx, ws, "word"))
        width += gap + ww * ws
    frag = []
    for (ox, by, bx, sc, kind) in parts:
        bh = _bbox(kind)[3]
        ty = y - bh * sc / 2
        frag.append(f'<g transform="translate({ox:.3f} {ty:.3f}) scale({sc:.6f}) '
                    f'translate({-bx:.4f} {-by:.4f})">'
                    f'{_group(kind, colour, dot_colour or colour)}</g>')
    if wordmark and number:
        d, adv = _number_path()
        size = height * 0.98                  # lining digits ~ wordmark ascenders x 0.74
        gap = 0.26 * height
        nx = width + gap
        # align the number's baseline with the wordmark's baseline
        _, wy, _, wh = _bbox("word")
        base = y + height * 0.95 / 2
        frag.append(f'<path transform="translate({nx:.3f} {base:.3f}) scale({size:.4f})" '
                    f'd="{d}" fill="{number_colour or colour}"/>')
        width = nx + adv * size
    if wordmark and descriptor:
        size = height * 0.36                  # capitals ~0.26 of the swirl
        gap = 0.46 * height
        d, adv = _text_path(descriptor, tracking=0.16)
        # centre the capitals on the wordmark's lowercase band (optical middle)
        wbase = y + height * 0.95 / 2         # the wordmark's baseline
        xmid = wbase - height * 0.95 * 0.70 / 2
        base = xmid + size * 0.72 / 2
        frag.append(f'<path transform="translate({width + gap:.3f} {base:.3f}) scale({size:.4f})" '
                    f'd="{d}" fill="{descriptor_colour or colour}" fill-opacity="0.72"/>')
        width = width + gap + adv * size
    if anchor == "middle":
        x -= width / 2
    body = "".join(frag)
    return (f'<g transform="translate({x:.3f} 0)" opacity="{opacity:.3f}">{body}</g>',
            width)
