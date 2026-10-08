# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""The Distributary design: one river network, two lighting moods.

Everything that defines the artwork lives here.  Change a value, rebuild,
and every wallpaper, login screen, boot splash and HDR master follows.
"""

import copy
import dataclasses
import functools

import numpy as np
from dataclasses import dataclass, field

from .network import Network, Params

# The river.  Seeded, so the same network is reproduced bit-for-bit.
NETWORK = Params(
    seed=6,
    root_width=0.02, min_width=0.0017, murray=2.4,
    meander_sigma=1.0, meander_tau=0.18,
    fan_gain=0.75, fan_back=0.6, k_flow=2.2, fan_tilt=-0.10,
    root_start=(-2.35, 0.20), apex=(-0.36, 0.05),
    # the main stem is drawn, not grown: a calm line into the first fork
    root_path=[(-2.35, 0.24), (-1.75, 0.16), (-1.2, 0.20), (-0.8, 0.13), (-0.36, 0.05)],
    split_len_k=22.0, split_len_min=0.08, terminal_len_k=(40.0, 110.0),
    forced=[{"ratio": 0.5, "angle": 0.78, "side": -1,
             "kids": [{"at": 0.30, "ratio": 0.55, "angle": 0.72, "side": 1},
                      {"at": 0.22, "ratio": 0.5, "angle": 0.66, "side": -1}]}],
)
SMOOTH = 6.0


@dataclass
class Palette:
    name: str
    # land, top -> bottom (world y): (y, colour)
    land: list
    # soft light pooled around the light: (colour, radius)
    haze: list
    # where the light sits (on the first fork, FORK_LIGHT) and its elliptical
    # reach (world units); "glint" is kept as the name saved palettes use
    glint: tuple
    glint_r: tuple
    # water radiance vs. normalised distance from the light: (d, colour, gain)
    # gain is in units of SDR reference white; > 1 only survives in HDR.
    water: list
    # halo around the channels: (sigma in world units, gain)
    glow: list
    # bank contour lines: (spacing, rings, gain, line width in world units)
    contours: tuple = (0.013, 5, 0.09, 0.00085)
    contour_smooth: float = 0.009
    # soft light along each channel's centre line, carried by the raster base
    # and seen through the (slightly translucent) vector channels:
    # (core width fraction, [(sigma in world units, gain), ...])
    core: tuple = (0.35, [(0.0012, 1.4), (0.0035, 0.6)])
    channel_opacity: float = 0.72
    # "add": halos are light (dark palettes); "tint": halos stain the land
    # toward the water colour (light palettes)
    glow_mode: str = "add"
    # tone curve: luminance below the knee is displayed as-is
    knee: float = 0.62
    # light palettes fade minor channels toward the paper instead of darkening
    fade_to: str = None
    # colour by distance along the river: (colour, fully tinted until this
    # distance from the source, untinted from this distance, gain)
    source_tint: tuple = None
    tint_levels: int = 32
    # thin channels carry a little less light
    width_gamma: float = 0.2
    width_floor: float = 0.5
    value_levels: int = 48
    # how the Debian logo is drawn over this palette
    logo_colour: str = "#ffffff"
    logo_opacity: float = 0.85


# The light sits on the first fork: the Y of "forky" is the brightest point,
# and the delta fades as it spreads away from it.
FORK_LIGHT = (-0.33, 0.04)

DUSK = Palette(
    name="dusk",
    land=[(-0.60, "#07081a"), (0.0, "#0b0b22"), (0.60, "#120d26")],
    haze=[("#16182c", 0.60), ("#0d0f2c", 1.40)],
    glint=FORK_LIGHT, glint_r=(1.0, 0.7),
    # white at the fork, then Debian rose, magenta, violet: no orange
    water=[(0.00, "#fff0f2", 2.80), (0.18, "#ffc2d0", 1.50), (0.40, "#ff7f9f", 1.15),
           (0.65, "#f0457c", 0.92), (0.95, "#d0357d", 0.78), (1.25, "#a63d93", 0.64),
           (1.60, "#7a3aa8", 0.50), (2.20, "#4b3a9c", 0.38)],
    glow=[(0.0025, 0.22), (0.010, 0.17), (0.040, 0.13), (0.14, 0.09)],
    core=(0.35, [(0.0012, 1.0), (0.0035, 0.45)]),
    contours=(0.013, 5, 0.15, 0.00085),
    width_floor=0.45, width_gamma=0.30,
)

DAWN = Palette(
    name="dawn",
    land=[(-0.60, "#f4f0f5"), (0.0, "#efeaf2"), (0.60, "#e7e0ec")],
    haze=[("#0c0a0a", 0.60), ("#040406", 1.40)],
    glint=FORK_LIGHT, glint_r=(1.0, 0.7),
    # the strongest ink, Debian red, at the fork; lighter and cooler outward
    water=[(0.00, "#c8104e", 1.0), (0.35, "#d23457", 1.0), (0.70, "#c8306e", 1.0),
           (1.05, "#a43a8c", 1.0), (1.45, "#7a3a9e", 1.0), (2.20, "#4f3a8a", 1.0)],
    glow=[(0.004, 0.10), (0.020, 0.07), (0.080, 0.05)],
    glow_mode="tint",
    contours=(0.013, 5, 0.20, 0.00085),
    core=(0.35, []),
    channel_opacity=0.92,
    width_floor=0.38, width_gamma=0.55,
    # flat ink shows the steps between levels that glow hides on Dusk
    value_levels=128,
    knee=0.98,
    fade_to="#efe9f1",
    logo_colour="#2b2342", logo_opacity=0.85,
)

PALETTES = {"dusk": DUSK, "dawn": DAWN}


@dataclass
class Design:
    palette: Palette
    params: Params = field(default_factory=lambda: copy.deepcopy(NETWORK))

    @property
    def root_width(self):
        return self.params.root_width

    @functools.cached_property
    def branches(self):
        return Network(copy.deepcopy(self.params)).grow().finalize(smooth=SMOOTH)

    @functools.cached_property
    def contours(self):
        from .contours import bank_contours
        spacing, rings, _, _ = self.palette.contours
        return bank_contours(self.branches, spacing=spacing, rings=rings,
                             smooth=self.palette.contour_smooth)

    def value_of_width(self, w):
        """Light carried by a channel of width w (continuous)."""
        p = self.palette
        r = np.maximum(np.asarray(w, dtype=float) / self.root_width, 1e-6)
        return np.maximum(p.width_floor, r ** p.width_gamma)

    def quantise(self, v):
        """Snap values to palette.value_levels steps (SVG needs a gradient each)."""
        p = self.palette
        n = p.value_levels - 1
        t = np.round((np.asarray(v) - p.width_floor) / (1 - p.width_floor) * n) / n
        return p.width_floor + t * (1 - p.width_floor)

    @functools.cached_property
    def offsets(self):
        """Distance along the river from the source to each channel's start."""
        by_id = {b["id"]: b for b in self.branches}
        off = {}
        for b in sorted(self.branches, key=lambda b: b["id"]):   # parents first
            par = by_id.get(b["parent"])
            off[b["id"]] = 0.0 if par is None else off.get(par["id"], 0.0) + par["s"][-1]
        return off

    def tint_at(self, s_abs):
        """Share of palette.source_tint carried at distance s_abs (quantised)."""
        st = self.palette.source_tint
        s_abs = np.asarray(s_abs, dtype=float)
        if not st:
            return np.zeros_like(s_abs)
        _, s_full, s_zero = st[:3]
        t = np.clip((s_zero - s_abs) / (s_zero - s_full), 0, 1)
        n = self.palette.tint_levels - 1
        return np.round(t * t * (3 - 2 * t) * n) / n

    @functools.cached_property
    def pieces(self):
        """Channels cut into runs of constant (quantised) light and tint.

        The value follows each channel's local width, so light changes
        smoothly across forks and fades out along tapering tips; the tint
        follows the distance along the river from the source.  Adjacent
        runs overlap by a point so they join without seams.
        """
        out = []
        for b in self.branches:
            # constant light per channel, eased in from the parent's across
            # the fork so there is no step where a channel splits
            v_own = self.value_of_width(b["width"])
            v_in = self.value_of_width(b["birth_width"])
            t = np.clip(b["s"] / max(6.0 * b["birth_width"], 1e-6), 0, 1)
            t = t * t * (3 - 2 * t)
            q = self.quantise(v_in + (v_own - v_in) * t)
            tint = self.tint_at(self.offsets[b["id"]] + b["s"])
            change = (np.diff(q) != 0) | (np.diff(tint) != 0)
            cuts = np.flatnonzero(change) + 1
            starts = np.concatenate([[0], cuts])
            ends = np.concatenate([cuts, [len(q)]])
            for s0, e0 in zip(starts, ends):
                a, e = max(0, s0 - 1), min(len(q), e0 + 1)
                if e - a < 2:
                    continue
                out.append(dict(x=b["x"][a:e], y=b["y"][a:e], w=b["w"][a:e],
                                value=float(q[s0]), tint=float(tint[s0]), width=b["width"]))
        return out

    @functools.cached_property
    def forks(self):
        """Round joints where channels split, lit and tinted like the
        incoming channel: dicts with x, y, width, value, tint."""
        out = []
        for b in self.branches:
            if b["parent"] >= 0:
                v = float(self.quantise(self.value_of_width(b["birth_width"])))
                t = float(self.tint_at(self.offsets[b["id"]]))
                out.append(dict(x=b["fx"], y=b["fy"], width=b["birth_width"], value=v, tint=t))
        return out

    def grown(self, front, contour_fade=0.0):
        """The river as it stands once the water has come `front` along it
        from the source: channels appear in order, their tips tapering."""
        grown = []
        for b in self.branches:
            s_abs = self.offsets[b["id"]] + b["s"]
            n = int(np.count_nonzero(s_abs <= front))
            if n < 2:
                continue
            u = np.clip((front - s_abs[:n]) / (8 * b["width"]), 0, 1)
            grown.append(dict(b, x=b["x"][:n], y=b["y"][:n], w=b["w"][:n] * np.sqrt(u),
                              s=b["s"][:n]))
        pal = copy.deepcopy(self.palette)
        spacing, rings, gain, lw = pal.contours
        pal.contours = (spacing, rings, gain * contour_fade, lw)
        d = Design(pal, params=self.params)
        d.__dict__["branches"] = grown
        d.__dict__["offsets"] = self.offsets
        d.__dict__["contours"] = self.contours if contour_fade > 0 else []
        # a joint appears once both sides of the fork have started to grow
        started = {b["id"] for b in grown
                   if front - self.offsets[b["id"]] > 3 * b["birth_width"]}
        owners = [b["id"] for b in self.branches if b["parent"] >= 0]   # forks order
        d.__dict__["forks"] = [f for f, bid in zip(self.forks, owners) if bid in started]
        return d

    def ring_alpha(self, k):
        _, rings, gain, _ = self.palette.contours
        return gain * max(0.0, 1 - (k - 0.6) / (rings + 0.5)) ** 1.5


@functools.lru_cache(maxsize=None)
def get(name="dusk"):
    return Design(PALETTES[name])


def use(dusk, dawn):
    """Build with these palettes (a colour option, say) from now on."""
    PALETTES.update(dusk=dusk, dawn=dawn)
    get.cache_clear()


def palette_to_json(pal):
    """A Palette as plain JSON data (what the palette editor reads and writes)."""
    data = dataclasses.asdict(pal)
    del data["name"]
    return data


def palette_from_json(data, name):
    """A Palette from JSON data; unknown keys are ignored, missing ones default."""
    known = {f.name for f in dataclasses.fields(Palette)} - {"name"}
    return Palette(name=name, **{k: v for k, v in data.items() if k in known})
