# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Alternative colour schemes, for comparison.

All of them keep the river and its light on the first fork; only colours
change.  The default already took two of the first round of options (a
neutral haze, no orange); what remains builds on it: midnight-blue land
instead of violet, and a cool paper for Dawn.

The bigger departures are standalone.  Colours that follow the river
itself (Long fade's red) use the palette's source_tint: they are measured
along the river from its source, so they land on the same channels on
every screen shape.

scheme(key) gives the palettes of any option, to build the whole theme
with (build.py --scheme KEY).
"""

import dataclasses
import functools

from . import design as D


@functools.lru_cache(maxsize=None)
def fork_distances():
    """Distance along the river from the source to the first fork, and to
    the nearer and the farther of the two forks that end the first branches."""
    d = D.get("dusk")
    root = d.branches[0]["id"]
    first = {b["id"] for b in d.branches if b["parent"] == root}
    second = [d.offsets[b["id"]] for b in d.branches if b["parent"] in first]
    return min(d.offsets[i] for i in first), min(second), max(second)


def _midnight(dusk, dawn):
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#050b1d"), (0.0, "#07102a"), (0.60, "#0b1633")],
        haze=[("#141a2e", 0.60), ("#0b1430", 1.40)])
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#f2f5f9"), (0.0, "#eaeff5"), (0.60, "#e1e8f0")],
        fade_to="#eaeff5", logo_colour="#1f2940")
    return dusk, dawn


STEPS = [
    ("midnight", "Midnight", "The ground turns midnight blue; Dawn's paper turns cool.", _midnight),
]


def schemes():
    """[(key, title, change, dusk Palette, dawn Palette)]: now, then the steps."""
    dusk, dawn = D.DUSK, D.DAWN
    out = [("current", "Original", "Violet ground, neutral haze, rose light from the fork.", dusk, dawn)]
    keys = []
    for key, title, change, step in STEPS:
        dusk, dawn = step(dusk, dawn)
        keys.append(key)
        label = "+".join(keys)
        out.append((label, title, change,
                    dataclasses.replace(dusk, name=f"dusk-option-{label}"),
                    dataclasses.replace(dawn, name=f"dawn-option-{label}")))
    return out


# -- bigger departures: standalone schemes, not built on the steps above --------

def _debian_red(dusk, dawn):
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#0a090d"), (0.0, "#0e0c11"), (0.60, "#131015")],
        haze=[("#1a1719", 0.60), ("#0f0d11", 1.40)],
        water=[(0.00, "#fff0f2", 2.80), (0.18, "#ffc6d2", 1.50), (0.40, "#ff7d9b", 1.15),
               (0.65, "#f23f6d", 0.92), (0.95, "#d70a53", 0.78), (1.25, "#b3073f", 0.64),
               (1.60, "#8c0634", 0.50), (2.20, "#6a0529", 0.38)])
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#fbf8f6"), (0.0, "#f6f2f0"), (0.60, "#efe9e6")],
        fade_to="#f6f2f0", logo_colour="#2a1c21",
        water=[(0.00, "#a8063d", 1.0), (0.35, "#c8104e", 1.0), (0.70, "#d7335f", 1.0),
               (1.05, "#d4557a", 1.0), (1.45, "#c26a88", 1.0), (2.20, "#a97a90", 1.0)])
    return dusk, dawn


def _rose_teal(dusk, dawn):
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#031315"), (0.0, "#05181b"), (0.60, "#071e21")],
        haze=[("#0c2426", 0.60), ("#06191c", 1.40)],
        water=[(0.00, "#fff4f1", 2.80), (0.18, "#ffd0d7", 1.50), (0.40, "#ff97ad", 1.15),
               (0.65, "#f6628b", 0.92), (0.95, "#e63d76", 0.78), (1.25, "#c93063", 0.64),
               (1.60, "#a9275a", 0.50), (2.20, "#86214d", 0.38)])
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#f2f6f5"), (0.0, "#ebf1ef"), (0.60, "#e2eae8")],
        fade_to="#ebf1ef", logo_colour="#18292a",
        water=[(0.00, "#b8235a", 1.0), (0.35, "#cf2d62", 1.0), (0.70, "#dc4a74", 1.0),
               (1.05, "#d8678a", 1.0), (1.45, "#c47d95", 1.0), (2.20, "#a88a96", 1.0)])
    return dusk, dawn


def _glacier(dusk, dawn):
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#040a12"), (0.0, "#061019"), (0.60, "#081520")],
        haze=[("#0b1b29", 0.60), ("#061425", 1.40)],
        water=[(0.00, "#effbff", 2.80), (0.18, "#c2f0ff", 1.50), (0.40, "#7ddaf5", 1.15),
               (0.65, "#44bce4", 0.92), (0.95, "#2c9ed4", 0.78), (1.25, "#2a80c3", 0.64),
               (1.60, "#2f62b0", 0.50), (2.20, "#2b4896", 0.38)])
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#f3f7fa"), (0.0, "#edf2f6"), (0.60, "#e5ecf2")],
        fade_to="#edf2f6", logo_colour="#16263a",
        water=[(0.00, "#133f7a", 1.0), (0.35, "#1d5095", 1.0), (0.70, "#2269ac", 1.0),
               (1.05, "#2b87bf", 1.0), (1.45, "#4a9dc6", 1.0), (2.20, "#6aa9c6", 1.0)])
    return dusk, dawn


def _silver_red(dusk, dawn, full, zero):
    """Silver water; Debian red from the source, fading out between
    `full` and `zero` along the river."""
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#07080c"), (0.0, "#0a0b10"), (0.60, "#0d0e14")],
        haze=[("#15161c", 0.60), ("#0c0d13", 1.40)],
        water=[(0.00, "#ffffff", 2.60), (0.18, "#eef2f8", 1.50), (0.40, "#d2dae7", 1.10),
               (0.70, "#a8b3c6", 0.86), (1.00, "#8e98ac", 0.70), (1.40, "#77829a", 0.56),
               (2.20, "#5d6780", 0.42)],
        source_tint=("#e0104f", full, zero, 0.95))
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#f8f8f7"), (0.0, "#f2f2f1"), (0.60, "#eaeae9")],
        fade_to="#f2f2f1", logo_colour="#1f2228",
        water=[(0.00, "#3f444d", 1.0), (0.35, "#4b515c", 1.0), (0.70, "#5f6570", 1.0),
               (1.05, "#767c87", 1.0), (1.45, "#8d929b", 1.0), (2.20, "#a4a8af", 1.0)],
        source_tint=("#c8104e", full, zero, 1.0))
    return dusk, dawn


# how far along the river the long fade takes to turn red into silver
LONG_FADE = 0.70


def _long_fade(dusk, dawn):
    # red through the first fork and its branches, then fading out slowly
    # across the next few generations of forks
    _, near, _ = fork_distances()
    return _silver_red(dusk, dawn, near, near + LONG_FADE)


def _forest(dusk, dawn):
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#041009"), (0.0, "#06150d"), (0.60, "#081b11")],
        haze=[("#0f2016", 0.60), ("#07170e", 1.40)],
        water=[(0.00, "#fff7e2", 2.80), (0.18, "#ffe9b6", 1.50), (0.40, "#f1d68f", 1.15),
               (0.65, "#d7c27d", 0.92), (0.95, "#b3b476", 0.76), (1.25, "#8ea572", 0.62),
               (1.60, "#6a9372", 0.50), (2.20, "#4d7f6a", 0.38)])
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#f2f6f0"), (0.0, "#eaf1e7"), (0.60, "#e1eadd")],
        fade_to="#eaf1e7", logo_colour="#1c2b22",
        water=[(0.00, "#184d35", 1.0), (0.35, "#1f5e44", 1.0), (0.70, "#2d7453", 1.0),
               (1.05, "#4a8865", 1.0), (1.45, "#6a9a7c", 1.0), (2.20, "#88a895", 1.0)])
    return dusk, dawn


def _silt(dusk, dawn):
    # a delta is built from the silt its river carries
    dusk = dataclasses.replace(
        dusk, land=[(-0.60, "#110c08"), (0.0, "#160f0a"), (0.60, "#1b130d")],
        haze=[("#211912", 0.60), ("#140e0a", 1.40)],
        water=[(0.00, "#fff6ea", 2.80), (0.18, "#f8e4c8", 1.50), (0.40, "#e8c59e", 1.15),
               (0.65, "#d0a176", 0.92), (0.95, "#b3825a", 0.78), (1.25, "#946747", 0.64),
               (1.60, "#765139", 0.50), (2.20, "#5a3e2d", 0.38)])
    dawn = dataclasses.replace(
        dawn, land=[(-0.60, "#f7f0e3"), (0.0, "#f2e9d9"), (0.60, "#eadfcc")],
        fade_to="#f2e9d9", logo_colour="#3a2a1d",
        water=[(0.00, "#3d2412", 1.0), (0.35, "#55321a", 1.0), (0.70, "#704520", 1.0),
               (1.05, "#8a5a2e", 1.0), (1.45, "#a0714a", 1.0), (2.20, "#b28a66", 1.0)])
    return dusk, dawn


DEPARTURES = [
    ("red", "Debian red", "The river in Debian's own red, on charcoal and on warm white paper.", _debian_red),
    ("teal", "Rose on teal", "Debian rose over deep teal land: complementary, with no purple or orange.", _rose_teal),
    ("glacier", "Glacier", "Cool cyan light on slate; blue ink on icy paper. No warm colours at all.", _glacier),
    ("long-fade", "Long fade",
     "A silver river on charcoal. Debian red runs through the first fork and its branches, "
     "then turns silver slowly over the next few forks.", _long_fade),
    ("forest", "Forest", "Deep green ground; white-gold light at the fork, turning sage as it spreads.", _forest),
    ("silt", "Silt", "Browns, like the silt a delta is built from: cream light on dark earth, "
     "sepia ink on parchment.", _silt),
]


def departures():
    """[(key, title, change, dusk Palette, dawn Palette)] for bigger changes."""
    out = []
    for key, title, change, fn in DEPARTURES:
        dusk, dawn = fn(D.DUSK, D.DAWN)
        out.append((key, title, change, dataclasses.replace(dusk, name=f"dusk-{key}"),
                    dataclasses.replace(dawn, name=f"dawn-{key}")))
    return out


def scheme(key):
    """(title, dusk Palette, dawn Palette) of any option, named for a build."""
    for k, title, _, dusk, dawn in schemes() + departures():
        if k == key:
            return (title, dataclasses.replace(dusk, name="dusk"),
                    dataclasses.replace(dawn, name="dawn"))
    raise KeyError(f"no colour option {key!r}")


def unlit(palette, at=0.6):
    """The palette without the light on the fork, as on Long fade: the water
    near the fork keeps the colour and brightness it has further out."""
    i = next(i for i, (d, *_) in enumerate(palette.water) if d >= at)
    water = [(0.0, *palette.water[i][1:])] + palette.water[i:]
    return dataclasses.replace(palette, water=water, name=f"{palette.name}-unlit")


def unlit_drafts():
    """[(key, title, dusk Palette, dawn Palette)]: every option that has the
    light on the fork, without it (Long fade has none to take away)."""
    return [(k, title, unlit(dusk), unlit(dawn))
            for k, title, _, dusk, dawn in schemes() + departures() if not dusk.source_tint]


def preview_slug(key):
    """File name stem of an option's previews on the showcase."""
    if key == "current":
        return "current"
    return ("option-" + key.replace("+", "-")) if key in {k for k, *_ in schemes()} else "alt-" + key


def design_for(palette):
    """A Design with this palette, sharing the (colour-independent) river."""
    base = D.get("dusk")
    d = D.Design(palette)
    d.__dict__["branches"] = base.branches
    d.__dict__["contours"] = base.contours
    d.__dict__["offsets"] = base.offsets
    return d
