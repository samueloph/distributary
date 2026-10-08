# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Shared geometry helpers: views (world -> pixels) and ribbon outlines."""

from dataclasses import dataclass

import numpy as np


@dataclass
class View:
    """A rectangular window onto the world, rendered at W x H pixels."""
    W: int
    H: int
    cx: float = 0.0
    cy: float = 0.0
    height: float = 1.0          # world units spanned vertically
    rotate: int = 0              # 0 or 90 (portrait: river flows downward)

    @property
    def width(self):
        return self.height * self.W / self.H

    @property
    def scale(self):             # pixels per world unit
        return self.H / self.height

    def to_px(self, x, y):
        if self.rotate == 90:    # world +x (downstream) maps to screen down
            x, y = -y, x
        px = (x - (self.cx - self.width / 2)) * self.scale
        py = (y - (self.cy - self.height / 2)) * self.scale
        return px, py


def ribbon(x, y, w):
    """Closed outline of a variable-width stroke along (x, y)."""
    tx = np.gradient(x)
    ty = np.gradient(y)
    n = np.hypot(tx, ty) + 1e-12
    nx, ny = -ty / n, tx / n
    h = 0.5 * w
    lx, ly = x + nx * h, y + ny * h
    rx, ry = x - nx * h, y - ny * h
    return np.concatenate([lx, rx[::-1]]), np.concatenate([ly, ry[::-1]])
