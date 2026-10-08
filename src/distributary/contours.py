# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Bank contours: iso-distance lines around the channels, in world space.

They are computed once per design on a fixed world grid, so every output
(any view, any resolution, raster or SVG) draws exactly the same lines.
"""

import numpy as np
from scipy import ndimage

from . import raster
from .geometry import View


def bank_contours(branches, spacing=0.013, rings=5, res=0.0015, smooth=0.006,
                  bounds=(-2.45, 2.45, -1.45, 1.45), tolerance=0.00035):
    """Return [(ring_index, polyline Nx2 world coords), ...]."""
    import contourpy

    x0, x1, y0, y1 = bounds
    W = int(round((x1 - x0) / res))
    H = int(round((y1 - y0) / res))
    view = View(W=W, H=H, cx=(x0 + x1) / 2, cy=(y0 + y1) / 2, height=H * res)
    _, cov = raster.rasterize(branches, view, lambda b: 1.0)
    dist = ndimage.distance_transform_edt(cov < 0.5) * res
    dist = ndimage.gaussian_filter(dist, smooth / res)
    gen = contourpy.contour_generator(z=dist, line_type="Separate")
    left = view.cx - view.width / 2
    top = view.cy - view.height / 2
    out = []
    for k in range(1, rings + 1):
        for line in gen.lines(spacing * k):
            if len(line) < 4:
                continue
            pts = np.empty_like(line)
            pts[:, 0] = left + (line[:, 0] + 0.5) * res
            pts[:, 1] = top + (line[:, 1] + 0.5) * res
            pts = _rdp(pts, tolerance)
            if len(pts) >= 3:
                out.append((k, pts))
    return out


def _rdp(pts, eps):
    """Ramer-Douglas-Peucker simplification (iterative)."""
    n = len(pts)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        seg = pts[i + 1:j] - a
        L = np.hypot(*ab)
        if L < 1e-12:
            d = np.hypot(seg[:, 0], seg[:, 1])
        else:
            d = np.abs(ab[0] * seg[:, 1] - ab[1] * seg[:, 0]) / L
        m = int(np.argmax(d))
        if d[m] > eps:
            k = i + 1 + m
            keep[k] = True
            stack.append((i, k))
            stack.append((k, j))
    return pts[keep]
