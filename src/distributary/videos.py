# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""The rendered videos.

    plymouth-boot       the boot splash as it plays, with a disk passphrase
    flow-dusk           the wallpaper with light flowing downstream (SDR, HDR)
    flow-dawn           the light variant, ink pulsing downstream
    river-growth        the delta drawing itself
    boot-to-desktop     GRUB, Plymouth, login and desktop in one take

Boot screens are simulations that follow the Plymouth script and GRUB's
default menu; wallpapers are rendered from the design, like the stills.
"""

import os
import time

import numpy as np

from . import design as D
from . import encode
from .animate import (LOSSLESS, Flow, GrubSim, Growth, PlymouthSim, VideoWriter,
                      encode_from, hdr_outputs, parallel_frames, plymouth_timeline,
                      sdr_outputs, to_pq_rgb16, to_video_rgb16)
from .geometry import View

FPS = 60
LOOP = 12.0          # seconds: the flow loops seamlessly
PULSE_PERIOD = 6.0   # a pulse passes any point every 6 s
PASSPHRASE = "Please unlock disk nvme0n1p3_crypt:"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


WORKERS = 5          # frame renderers; memory, not cores, is the limit at 4K


def _encode(W, H, outputs, frames, tmp):
    """Frames -> lossless intermediate -> each deliverable in turn."""
    master = os.path.join(tmp, "master.mkv")
    w = VideoWriter(W, H, FPS, [(master, LOSSLESS)])
    for f in frames:
        w.write(f)
    w.close()
    res = encode_from(master, outputs)
    os.unlink(master)
    return res


def _report(results, t0):
    for path, size in results:
        log(f"video {os.path.basename(path):44s} {size / 1e6:6.1f} MB")
    log(f"      ({time.time() - t0:.0f}s)")


# -- boot splash -------------------------------------------------------------------

def plymouth_scenario(luks=True):
    """(duration, target from, target to, prompt, typing) segments.

    Plymouth freezes boot progress while it asks for a passphrase.
    """
    if not luks:
        return [(5.0, 0.0, 1.0, None, None), (0.8, 1.0, 1.0, None, None)]
    return [(1.2, 0.0, 0.05, None, None),
            (0.5, 0.05, 0.05, PASSPHRASE, None),
            (2.4, 0.05, 0.05, PASSPHRASE, (0.2, 2.0, 14)),
            (0.35, 0.05, 0.05, PASSPHRASE, (-1.0, -0.5, 14)),
            (6.5, 0.05, 1.0, None, None),
            (1.0, 1.0, 1.0, None, None)]


def plymouth_video(out, tmp, theme, login):
    t0 = time.time()
    W, H = 1920, 1080
    sim = PlymouthSim(os.path.join(theme, "plymouth"), W, H)
    login_img = login(W, H)
    seq = [("black",)] * round(0.8 * FPS)
    seq += [("ply", s, p, b) for s, p, b in plymouth_timeline(sim, FPS, plymouth_scenario())]
    last = seq[-1][1]
    n = round(0.8 * FPS)
    seq += [("mix", last, ease(i / (n - 1))) for i in range(n)]
    seq += [("login",)] * round(1.5 * FPS)
    black = np.zeros((H, W, 3), np.float32)

    def frame(d):
        if d[0] == "black":
            img = black
        elif d[0] == "ply":
            img = sim.image(d[1], d[2], d[3])
        elif d[0] == "mix":
            img = sim.image(d[1]) * (1 - d[2]) + login_img * d[2]
        else:
            img = login_img
        return to_video_rgb16(img)

    res = _encode(W, H, sdr_outputs(os.path.join(out, "plymouth-boot"), W, H, FPS),
                  parallel_frames(frame, seq, workers=WORKERS), tmp)
    _report(res, t0)


# -- the wallpaper, flowing ------------------------------------------------------------

def flow_video(out, tmp, name, W, H, logo_for, hdr=False):
    t0 = time.time()
    des = D.get(name)
    view = View(W=W, H=H)
    flow = Flow(view, des, logo=logo_for(W, H, des), amplitude=0.85)
    log(f"flow-{name}: precomputed {W}x{H} in {time.time() - t0:.0f}s")
    times = [i / FPS for i in range(round(LOOP * FPS))]
    stem = os.path.join(out, f"wallpaper-flow-{name}")
    sdr_master = os.path.join(tmp, "sdr.mkv")
    hdr_master = os.path.join(tmp, "hdr.mkv")
    sdr_w = VideoWriter(W, H, FPS, [(sdr_master, LOSSLESS)])
    hdr_w = VideoWriter(W, H, FPS, [(hdr_master, LOSSLESS)]) if hdr else None
    if hdr:
        maxcll, maxfall = _hdr_levels(des, logo_for)
        log(f"flow-{name}: HDR MaxCLL {maxcll:.0f} MaxFALL {maxfall:.1f}")

    def frame(t):
        sdr, lin = flow.frame(t, PULSE_PERIOD, hdr=hdr)
        return to_video_rgb16(sdr), (to_pq_rgb16(lin) if hdr else None)

    for sdr16, pq16 in parallel_frames(frame, times, workers=WORKERS):
        sdr_w.write(sdr16)
        if hdr_w:
            hdr_w.write(pq16)
    sdr_w.close()
    if hdr_w:
        hdr_w.close()
    log(f"flow-{name}: rendered {len(times)} frames ({time.time() - t0:.0f}s), encoding")
    res = encode_from(sdr_master, sdr_outputs(stem, W, H, FPS))
    if hdr:
        res += encode_from(hdr_master, hdr_outputs(stem, H, FPS, maxcll, maxfall))
        os.unlink(hdr_master)
    os.unlink(sdr_master)
    _report(res, t0)


def _hdr_levels(des, logo_for, samples=24):
    """MaxCLL/MaxFALL of the loop, measured on a quarter-size render."""
    W, H = 960, 540
    flow = Flow(View(W=W, H=H), des, logo=logo_for(W, H, des), amplitude=0.85)
    cll = fall = 0.0
    for i in range(samples):
        _, lin = flow.frame(i * PULSE_PERIOD / samples, PULSE_PERIOD, hdr=True)
        c, f = encode.light_levels(lin, 1000.0)
        cll, fall = max(cll, c), max(fall, f)
    return cll, fall


# -- the river, growing ----------------------------------------------------------------

def growth_video(out, tmp, logo_for):
    t0 = time.time()
    W, H = 1920, 1080
    des = D.get("dusk")
    view = View(W=W, H=H)
    logo = logo_for(W, H, des)
    growth = Growth(view, des, logo=logo)
    s0, s1 = growth.s_enter - 0.02, growth.s_full
    seq = [("grow", s0, 0.0, 0.0)] * round(0.6 * FPS)
    n = round(7.0 * FPS)
    seq += [("grow", s0 + (s1 - s0) * ease(i / (n - 1)) ** 0.9, 0.0, 0.0) for i in range(n)]
    n = round(1.6 * FPS)
    seq += [("grow", s1, ease(i / (n - 1)), ease(i / (n - 1))) for i in range(n)]
    # then the finished wallpaper holds, still
    seq += [("grow", s1, 1.0, 1.0)] * round(3.0 * FPS)

    def frame(d):
        return to_video_rgb16(growth.frame(d[1], contour_fade=d[2], logo_fade=d[3]))

    res = _encode(W, H, sdr_outputs(os.path.join(out, "river-growth"), W, H, FPS),
                  parallel_frames(frame, seq, workers=WORKERS), tmp)
    _report(res, t0)


# -- boot to desktop ------------------------------------------------------------------

def boot_to_desktop_video(out, tmp, theme, login, logo_for):
    t0 = time.time()
    W, H = 1920, 1080
    des = D.get("dusk")
    grub = GrubSim(os.path.join(theme, "grub", "grub-16x9.png"), W, H)
    sim = PlymouthSim(os.path.join(theme, "plymouth"), W, H)
    login_img = login(W, H)
    growth = Growth(View(W=W, H=H), des, logo=logo_for(W, H, des))
    desktop = growth.frame(growth.s_full, contour_fade=1.0, logo_fade=1.0)
    seq = []
    for left in (3, 2, 1):
        seq += [("grub", left)] * FPS
    seq += [("black",)] * round(0.5 * FPS)
    seq += [("ply", s, p, b) for s, p, b in plymouth_timeline(sim, FPS, plymouth_scenario(luks=False))]
    last = seq[-1][1]
    n = round(0.7 * FPS)
    seq += [("ply-login", last, ease(i / (n - 1))) for i in range(n)]
    seq += [("login",)] * round(1.6 * FPS)
    n = round(0.9 * FPS)
    seq += [("login-desktop", ease(i / (n - 1))) for i in range(n)]
    seq += [("desktop",)] * round(3.0 * FPS)
    black = np.zeros((H, W, 3), np.float32)

    def frame(d):
        k = d[0]
        if k == "grub":
            img = grub.image(d[1])
        elif k == "black":
            img = black
        elif k == "ply":
            img = sim.image(d[1], d[2], d[3])
        elif k == "ply-login":
            img = sim.image(d[1]) * (1 - d[2]) + login_img * d[2]
        elif k == "login":
            img = login_img
        elif k == "login-desktop":
            img = login_img * (1 - d[1]) + desktop * d[1]
        else:
            img = desktop
        return to_video_rgb16(img)

    res = _encode(W, H, sdr_outputs(os.path.join(out, "boot-to-desktop"), W, H, FPS),
                  parallel_frames(frame, seq, workers=WORKERS), tmp)
    _report(res, t0)


def build(out, tmp, theme, login, logo_for, which=None):
    """Render the videos into `out`; lossless intermediates go to `tmp`."""
    os.makedirs(out, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    jobs = {
        "plymouth-boot": lambda: plymouth_video(out, tmp, theme, login),
        "river-growth": lambda: growth_video(out, tmp, logo_for),
        "boot-to-desktop": lambda: boot_to_desktop_video(out, tmp, theme, login, logo_for),
        # the flowing loops are off the site for now; still built on request
        "flow-dusk": lambda: flow_video(out, tmp, "dusk", 3840, 2160, logo_for, hdr=True),
        "flow-dawn": lambda: flow_video(out, tmp, "dawn", 3840, 2160, logo_for),
    }
    default = ("plymouth-boot", "river-growth", "boot-to-desktop")
    for name in which or ():
        if name not in jobs:
            log(f"video: no video called {name!r}; choose from {', '.join(jobs)}")
    for name, job in jobs.items():
        if (which is None and name in default) or (which and name in which):
            job()

