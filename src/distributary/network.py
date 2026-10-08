# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Procedural river-delta ("distributary") network.

World coordinates: the 16:9 reference frame is x in [-8/9, 8/9], y in
[-1/2, 1/2], y pointing down.  Every output (any aspect ratio, any
resolution, raster or SVG) is a view onto this same world, so all variants
share one geometry.

The network grows from a single channel entering from the left.  Channels
meander (Ornstein-Uhlenbeck curvature), steer along a gentle fan-shaped flow
field, avoid each other, and bifurcate: every junction is a fork.  Widths
follow Murray's law, so flow is conserved across each split.
"""

import math
from dataclasses import dataclass, field

import numpy as np

TAU = 2.0 * math.pi


def angdiff(a, b):
    """Signed smallest angle a - b, in (-pi, pi]."""
    return (a - b + math.pi) % TAU - math.pi


@dataclass
class Params:
    seed: int = 14
    ds: float = 0.0025                  # growth step (world units)
    root_start: tuple = (-2.35, 0.03)
    root_heading: float = 0.0
    root_width: float = 0.0125
    apex: tuple = (-0.40, -0.03)        # where the first fork happens
    min_width: float = 0.0010
    murray: float = 3.0                 # w^n conserved across a split
    split_len_k: float = 26.0           # distance between forks ~ k * width
    split_len_min: float = 0.035
    split_len_jitter: tuple = (0.55, 1.45)
    split_angle: tuple = (0.55, 1.00)   # total divergence at a fork (rad)
    flow_ratio: tuple = (0.28, 0.72)    # share of flow taken by child A
    meander_sigma: float = 2.4          # stationary curvature std (1/unit)
    meander_tau: float = 0.10           # curvature correlation length
    k_flow: float = 1.6                 # steering toward the flow field
    k_rep: float = 9.0                  # steering away from neighbours
    gap_min: float = 0.0030             # hard minimum gap between channels
    rep_extra: float = 0.030            # repulsion reach beyond the edges
    fan_back: float = 0.55              # virtual apex distance behind apex
    fan_gain: float = 1.0               # >1 widens the fan
    bounds: tuple = (-2.45, 2.45, -1.45, 1.45)
    terminal_len_k: tuple = (18.0, 45.0)  # run-out length of thinnest channels
    max_steps: int = 400000
    stub_len: float = 0.05              # dead ends shorter than this are pruned
    stub_len_k: float = 25.0
    thin_angle_scale: float = 0.6       # thin channels fork at narrower angles
    join: bool = True                   # colliding channels merge (braids)
    join_min_ratio: float = 0.0
    join_max_angle: float = 0.75        # only merge when converging gently
    island_min: float = 0.16            # no rejoining right after a fork
    root_meander: float = 1.6           # the main stem swings more, slowly
    root_meander_tau: float = 0.35
    width_wobble: float = 0.12          # slow +-12% width variation
    fan_tilt: float = 0.0               # rotate the fan axis (rad, <0 = up)
    run_out_meander: float = 0.5        # meander scale on terminal channels
    meander_thin_gain: float = 1.0      # extra meander for thin channels (cap)
    forced: list = field(default_factory=list)  # art-directed first forks
    root_path: list = field(default_factory=list)  # designed main stem (spline)


@dataclass
class Branch:
    id: int
    parent: int
    gen: int
    width: float
    birth_width: float
    heading: float
    xs: list = field(default_factory=list)
    ys: list = field(default_factory=list)
    children: list = field(default_factory=list)
    alive: bool = True
    ended_by: str = ""
    curv: float = 0.0
    since_split: float = 0.0
    split_len: float = 1.0
    terminal: bool = False
    run_out: float = 0.0
    join_width: float = 0.0
    forced: dict = None


class _Grid:
    def __init__(self, cell):
        self.cell = cell
        self.cells = {}

    def add(self, x, y, item):
        key = (math.floor(x / self.cell), math.floor(y / self.cell))
        self.cells.setdefault(key, []).append(item)

    def query(self, x, y, r):
        c = self.cell
        for i in range(math.floor((x - r) / c), math.floor((x + r) / c) + 1):
            for j in range(math.floor((y - r) / c), math.floor((y + r) / c) + 1):
                yield from self.cells.get((i, j), ())


class Network:
    def __init__(self, params: Params):
        self.p = params
        self.rng = np.random.default_rng(params.seed)
        self.branches = []
        self.grid = _Grid(0.02)
        self.max_width = params.root_width

    # -- helpers ---------------------------------------------------------
    def _split_len(self, w):
        p = self.p
        lo, hi = p.split_len_jitter
        return max(p.split_len_min, p.split_len_k * w * self.rng.uniform(lo, hi))

    def _new_branch(self, parent, gen, width, birth_width, heading, x, y,
                    forced=None):
        b = Branch(id=len(self.branches), parent=parent, gen=gen, width=width,
                   birth_width=birth_width, heading=heading, forced=forced)
        b.xs.append(x)
        b.ys.append(y)
        b.split_len = self._split_len(width)
        if forced is not None and "at" in forced:
            b.split_len = forced["at"]
        if width * 0.62 < self.p.min_width:        # cannot fork any more
            b.terminal = True
            lo, hi = self.p.terminal_len_k
            b.run_out = width * self.rng.uniform(lo, hi)
        self.branches.append(b)
        return b

    def _flow_heading(self, x, y):
        p = self.p
        ax, ay = p.apex
        if x < ax:
            # upstream: drift gently toward the apex line
            return math.atan2((ay - y) * 1.2, 1.0) + 0.5 * p.fan_tilt
        vx = ax - p.fan_back
        # radial from a virtual apex, measured around the (tilted) fan axis
        rel = angdiff(math.atan2(y - ay, x - vx), p.fan_tilt)
        return p.fan_tilt + p.fan_gain * rel

    # -- growth ----------------------------------------------------------
    def grow(self):
        p = self.p
        x0, y0 = p.root_start
        forced = p.forced[0] if p.forced else None
        root = self._new_branch(-1, 0, p.root_width, p.root_width,
                                p.root_heading, x0, y0, forced)
        # root forks at the apex, not before
        root.split_len = (forced or {}).get("at", p.apex[0] - x0)
        self.grid.add(x0, y0, (x0, y0, root.width, root.id, 0))
        alive = [root]
        steps = 0
        if p.root_path:
            xs, ys = _spline(p.root_path, p.ds)
            root.xs, root.ys = list(xs), list(ys)
            for i in range(1, len(xs)):
                self.grid.add(xs[i], ys[i], (xs[i], ys[i], root.width, root.id, i))
            root.heading = math.atan2(ys[-1] - ys[-2], xs[-1] - xs[-2])
            self._fork(root)
            alive = [self.branches[c] for c in root.children]
        while alive and steps < p.max_steps:
            nxt = []
            for b in alive:
                steps += 1
                if self._step(b):
                    nxt.append(b)
                if not b.alive:
                    nxt.extend(self.branches[c] for c in b.children)
            alive = nxt
        return self

    def _step(self, b):
        p = self.p
        rng = self.rng
        ds = p.ds
        x, y, th, w = b.xs[-1], b.ys[-1], b.heading, b.width

        # neighbourhood: repulsion + collision
        sx, sy = b.xs[0], b.ys[0]
        exempt_r = max(4.0 * b.birth_width, 0.012)
        qr = 0.5 * (w + self.max_width) + p.rep_extra
        rx = ry = 0.0
        for (qx, qy, qw, qb, qi) in self.grid.query(x, y, qr):
            if qb == b.id:
                continue
            if (qx - sx) ** 2 + (qy - sy) ** 2 < exempt_r ** 2:
                continue
            dx, dy = x - qx, y - qy
            d = math.hypot(dx, dy) + 1e-12
            if d < 0.5 * (w + qw) + p.gap_min:
                b.alive = False
                other = self.branches[qb]
                oth = _heading_at(other, qi)
                own_len = (len(b.xs) - 1) * p.ds
                if (p.join and qw >= p.join_min_ratio * w
                        and own_len > p.island_min
                        and abs(angdiff(th, oth)) < p.join_max_angle):
                    self._merge(b, other, qi)
                    b.ended_by = "join"
                    b.join_width = qw
                else:
                    b.ended_by = "collision"
                return False
            reach = 0.5 * (w + qw) + p.rep_extra
            if d < reach:
                s = (1.0 - d / reach) ** 2
                rx += dx / d * s
                ry += dy / d * s

        # meander: OU process on curvature, stronger for thin channels
        sig = p.meander_sigma * min(p.meander_thin_gain,
                                    math.sqrt(0.004 / max(w, 1e-4)))
        tau = p.meander_tau
        if b.gen == 0:
            sig, tau = p.root_meander, p.root_meander_tau
        a = math.exp(-ds / tau)
        if b.terminal:
            sig *= p.run_out_meander
        b.curv = b.curv * a + sig * math.sqrt(1 - a * a) * rng.standard_normal()

        phi = self._flow_heading(x, y)
        nxv, nyv = -math.sin(th), math.cos(th)
        rep_turn = rx * nxv + ry * nyv
        th += ds * (b.curv + p.k_flow * angdiff(phi, th) + p.k_rep * rep_turn)
        # never flow back upstream
        lim = 1.25
        if abs(angdiff(th, 0.0)) > lim:
            th = math.copysign(lim, angdiff(th, 0.0))
        b.heading = th

        x += ds * math.cos(th)
        y += ds * math.sin(th)
        b.xs.append(x)
        b.ys.append(y)
        self.grid.add(x, y, (x, y, w, b.id, len(b.xs) - 1))
        b.since_split += ds

        x0b, x1b, y0b, y1b = p.bounds
        if not (x0b < x < x1b and y0b < y < y1b):
            b.alive = False
            b.ended_by = "bounds"
            return False

        if b.terminal:
            if b.since_split >= b.run_out:
                b.alive = False
                b.ended_by = "tip"
                return False
            return True

        if b.since_split >= b.split_len:
            self._fork(b)
            return False
        return True

    def _merge(self, b, other, qi):
        """Curve smoothly into `other`, a few widths downstream of node qi."""
        p = self.p
        ahead = max(3, int(4.0 * max(b.width, other.width) / p.ds))
        ti = min(qi + ahead, len(other.xs) - 1)
        tx, ty = other.xs[ti], other.ys[ti]
        x0, y0 = b.xs[-1], b.ys[-1]
        dist = math.hypot(tx - x0, ty - y0)
        # quadratic Bezier: leave along our heading, arrive on their course
        cx = x0 + math.cos(b.heading) * dist * 0.5
        cy = y0 + math.sin(b.heading) * dist * 0.5
        n = max(2, int(dist / p.ds))
        for k in range(1, n + 1):
            t = k / n
            b.xs.append((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * tx)
            b.ys.append((1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * ty)

    def _fork(self, b):
        p = self.p
        rng = self.rng
        f = b.forced or {}
        r = f.get("ratio", rng.uniform(*p.flow_ratio))
        n = p.murray
        wa = b.width * r ** (1.0 / n)
        wb = b.width * (1.0 - r) ** (1.0 / n)
        thin = min(1.0, b.width / (0.35 * p.root_width))
        scale = p.thin_angle_scale + (1.0 - p.thin_angle_scale) * thin
        alpha = f.get("angle", rng.uniform(*p.split_angle) * scale)
        # the larger child keeps closer to the parent's heading
        side = f.get("side", 1.0 if rng.random() < 0.5 else -1.0)
        tha = b.heading + side * alpha * (1.0 - r)
        thb = b.heading - side * alpha * r
        x, y = b.xs[-1], b.ys[-1]
        kids = f.get("kids", [None, None])
        b.alive = False
        b.ended_by = "fork"
        for wc, thc, fc in ((wa, tha, kids[0]), (wb, thb, kids[1])):
            if wc < p.min_width:
                continue
            c = self._new_branch(b.id, b.gen + 1, wc, b.width, thc, x, y, fc)
            c.curv = b.curv * 0.5
            b.children.append(c.id)
        if not b.children:
            b.ended_by = "tip"

    # -- post-processing ---------------------------------------------------
    def _is_stub(self, b):
        """Short dead-end channels read as thorns; drop them."""
        if b.ended_by not in ("collision", "tip") or b.children:
            return False
        length = len(b.xs) * self.p.ds
        return length < max(self.p.stub_len, self.p.stub_len_k * b.width)

    def finalize(self, smooth=3.0, resample=0.0012):
        """Smooth centre lines and compute per-point widths.

        Returns a list of dicts: x, y, w (arrays), gen, id, parent, ended_by,
        flow (relative to the root, Murray-weighted).
        """
        p = self.p
        out = []
        n = p.murray
        for b in self.branches:
            xs = np.asarray(b.xs)
            ys = np.asarray(b.ys)
            if len(xs) < 3:
                continue
            if self._is_stub(b):
                continue
            fx, fy = b.xs[0], b.ys[0]          # fork point (true junction)
            # prepend the parent's previous point so the junction is smooth
            if b.parent >= 0:
                pb = self.branches[b.parent]
                if len(pb.xs) >= 2:
                    xs = np.concatenate([[pb.xs[-2]], xs])
                    ys = np.concatenate([[pb.ys[-2]], ys])
            xs, ys = _smooth_polyline(xs, ys, smooth)
            xs, ys, s = _resample(xs, ys, resample)
            if len(xs) < 3:
                continue
            L = s[-1]
            # width: blend from parent width at the fork, taper at tips
            w = np.full_like(s, b.width)
            lb = max(5.0 * b.birth_width, 0.01)
            t = np.clip(s / lb, 0, 1)
            t = t * t * (3 - 2 * t)
            w = b.birth_width + (b.width - b.birth_width) * t
            if b.ended_by in ("tip", "collision"):
                lt = min(0.6 * L, (40.0 if b.ended_by == "tip" else 30.0) * b.width)
                u = np.clip((L - s) / max(lt, 1e-6), 0, 1)
                w = w * (u * u * (3 - 2 * u)) ** 0.8
            if p.width_wobble > 0 and L > 0.02:
                k = max(2, int(L / 0.06) + 2)
                knots = 1.0 + p.width_wobble * self.rng.uniform(-1, 1, k)
                knots[0] = 1.0                   # stay continuous at the fork
                w = w * np.interp(s, np.linspace(0, L, k), knots)
            if b.ended_by == "join":
                # blend toward a slim throat where it meets the neighbour
                lj = min(0.4 * L, 6.0 * b.width)
                u = np.clip((L - s) / max(lj, 1e-6), 0, 1)
                u = u * u * (3 - 2 * u)
                w = w * (0.7 + 0.3 * u)
            out.append(dict(id=b.id, parent=b.parent, gen=b.gen, x=xs, y=ys,
                            w=w, s=s, width=b.width, ended_by=b.ended_by,
                            birth_width=b.birth_width, fx=fx, fy=fy,
                            flow=(b.width / p.root_width) ** n))
        return out


def _spline(points, step):
    """Smooth curve through control points, sampled every `step`."""
    from scipy.interpolate import CubicSpline
    pts = np.asarray(points, dtype=float)
    t = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    cs = CubicSpline(t, pts, bc_type="natural")
    dense = cs(np.linspace(0, t[-1], 4000))
    xs, ys, _ = _resample(dense[:, 0], dense[:, 1], step)
    return xs, ys


def _heading_at(b, i):
    i = max(1, min(i, len(b.xs) - 1))
    return math.atan2(b.ys[i] - b.ys[i - 1], b.xs[i] - b.xs[i - 1])


def _smooth_polyline(xs, ys, sigma):
    if sigma <= 0 or len(xs) < 5:
        return xs, ys
    from scipy.ndimage import gaussian_filter1d
    x2 = gaussian_filter1d(xs, sigma, mode="nearest")
    y2 = gaussian_filter1d(ys, sigma, mode="nearest")
    # keep the endpoints exactly (junctions must stay connected)
    k = min(len(xs) // 2, int(3 * sigma) + 1)
    wgt = np.ones_like(xs)
    ramp = np.linspace(0, 1, k)
    wgt[:k] = ramp
    wgt[len(xs) - k:] = np.minimum(wgt[len(xs) - k:], ramp[::-1])
    x2 = xs + (x2 - xs) * wgt
    y2 = ys + (y2 - ys) * wgt
    return x2, y2


def _resample(xs, ys, step):
    d = np.hypot(np.diff(xs), np.diff(ys))
    s = np.concatenate([[0.0], np.cumsum(d)])
    if step <= 0 or s[-1] <= step:
        return xs, ys, s
    m = max(3, int(math.ceil(s[-1] / step)) + 1)
    si = np.linspace(0, s[-1], m)
    return np.interp(si, s, xs), np.interp(si, s, ys), si


def build(params: Params = None):
    params = params or Params()
    net = Network(params).grow()
    return net.finalize()
