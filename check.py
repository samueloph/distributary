#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Verify the build: SVGs in four renderers, HDR files' signalling.

    ./check.py            # report to stdout, side-by-side renders in build/check/

Renderers: librsvg (GNOME, Xfce), Qt SVG (KDE Plasma, SDDM), resvg, Inkscape.
Each SVG is rendered at its nominal size and compared with librsvg.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")
THEME = os.path.join(BUILD, "distributary-theme")


def render_librsvg(path, W, H):
    import cairo
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    Rsvg.Handle.new_from_file(path).render_document(cairo.Context(surf), vp)
    surf.flush()
    a = np.ndarray((H, surf.get_stride() // 4, 4), dtype=np.uint8, buffer=surf.get_data())
    return np.array(a[:, :W, [2, 1, 0]])


def render_qt(path, W, H):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication(["check", "-platform", "offscreen"])
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor(0, 0, 0))
    r = QSvgRenderer(path)
    if not r.isValid():
        raise RuntimeError("Qt SVG could not parse the file")
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, W, H))
    p.end()
    ptr = img.constBits()
    ptr.setsize(H * img.bytesPerLine())
    a = np.frombuffer(ptr, dtype=np.uint8).reshape(H, img.bytesPerLine() // 4, 4)
    return np.array(a[:, :W, [2, 1, 0]])


def _via_png(cmd, W, H):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.png")
        subprocess.run([c.replace("@OUT@", out) for c in cmd], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return np.asarray(Image.open(out).convert("RGB").resize((W, H)))


def render_resvg(path, W, H):
    return _via_png(["resvg", "-w", str(W), "-h", str(H), path, "@OUT@"], W, H)


def render_inkscape(path, W, H):
    return _via_png(["inkscape", path, "--export-type=png", "--export-filename=@OUT@",
                     f"--export-width={W}", f"--export-height={H}"], W, H)


RENDERERS = [("librsvg", render_librsvg, None), ("Qt SVG", render_qt, "PyQt6.QtSvg"),
             ("resvg", render_resvg, "resvg"), ("Inkscape", render_inkscape, "inkscape")]


def available(req):
    if req is None:
        return True
    if "." in req:
        import importlib.util
        try:
            return importlib.util.find_spec(req) is not None
        except ModuleNotFoundError:
            return False
    return shutil.which(req) is not None


def check_svgs(files, scale=0.5):
    out_dir = os.path.join(BUILD, "check")
    os.makedirs(out_dir, exist_ok=True)
    ok = True
    for path in files:
        name = os.path.relpath(path, BUILD)
        from xml.etree import ElementTree
        root = ElementTree.parse(path).getroot()
        # large wallpapers at half size; small banners at 2x so thin lines
        # and the logo are compared, not sub-pixel anti-aliasing
        k = scale if float(root.get("width")) >= 1280 else 2.0
        W = round(float(root.get("width")) * k)
        H = round(float(root.get("height")) * k)
        renders = {}
        for label, fn, req in RENDERERS:
            if available(req):
                try:
                    renders[label] = fn(path, W, H)
                except Exception as e:           # report, keep checking
                    print(f"  {label:9s} FAILED: {e}")
                    ok = False
        ref = renders["librsvg"]
        parts = []
        for label, img in renders.items():
            diff = np.abs(img.astype(int) - ref.astype(int))
            bad = (diff.max(axis=-1) > 24).mean() * 100
            parts.append(f"{label} {diff.mean():.2f}/{bad:.2f}%")
            if label != "librsvg" and (diff.mean() > 3.0 or bad > 1.0):
                ok = False
        print(f"{name}\n    mean diff / pixels off by >24 levels: " + ", ".join(parts))
        sheet = np.concatenate(list(renders.values()), axis=1)
        Image.fromarray(sheet).save(os.path.join(out_dir, name.replace("/", "_") + ".png"))
    return ok


def check_hdr():
    ok = True
    for avif in sorted(glob.glob(os.path.join(BUILD, "hdr", "*.avif"))):
        info = subprocess.run(["avifdec", "--info", avif], capture_output=True, text=True).stdout
        want = ["Gain map       : " if "gainmap" in avif else "Transfer Char. : 16"]
        good = all(w in info for w in want)
        ok &= good
        print(f"{os.path.basename(avif):48s} {'ok' if good else 'MISSING HDR SIGNALLING'}")
    for jxl in sorted(glob.glob(os.path.join(BUILD, "hdr", "*.jxl"))):
        info = subprocess.run(["jxlinfo", jxl], capture_output=True, text=True).stdout
        good = "PQ transfer function" in info
        ok &= good
        print(f"{os.path.basename(jxl):48s} {'ok' if good else 'NOT PQ'}")
    for meta in sorted(glob.glob(os.path.join(BUILD, "hdr", "*-hdr.json"))):
        m = json.load(open(meta))
        print(f"{os.path.basename(meta):48s} MaxCLL {m['MaxCLL']} MaxFALL {m['MaxFALL']}")
    return ok


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=codec_name,width,height,r_frame_rate,pix_fmt,"
                          "color_transfer,color_primaries,nb_read_frames", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def _all_frames(path, W=480, H=270):
    """Decode every frame, in order, at thumbnail size (seeking by frame
    index is unreliable with B-frame reordering)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf",
                          f"scale={W}:{H}:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(np.float32)


def check_videos():
    ok = True
    for path in sorted(glob.glob(os.path.join(ROOT, "media", "*.mp4"))):
        name = os.path.basename(path)
        st = _probe(path)
        hdr = "-hdr" in name
        want_trc = "smpte2084" if hdr else "bt709"
        good = st.get("color_transfer") == want_trc and st.get("color_primaries") == (
            "bt2020" if hdr else "bt709")
        note = ""
        if hdr:
            side = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                   "-show_frames", "-read_intervals", "%+#1", "-show_entries",
                                   "frame=side_data_list", path],
                                  capture_output=True, text=True).stdout
            good &= "Mastering display" in side or "mastering" in side.lower()
        if "wallpaper-flow" in name:
            # a seamless loop: last -> first must look like any other step.
            # The largest steps are keyframe refreshes, and the loop point is
            # one; open-GOP encoders (x265) smooth in-video keyframes more
            # than the hard start, so also accept anything under half a code
            # value on average, far below a visible flicker.
            v = _all_frames(path)
            steps = np.abs(np.diff(v, axis=0)).mean(axis=(1, 2, 3))
            wrap = float(np.abs(v[0] - v[-1]).mean())
            good &= wrap <= max(1.25 * float(steps.max()), 0.5)
            note = f"  loop seam {wrap:.2f} vs largest step {steps.max():.2f}"
        ok &= good
        print(f"{name:44s} {st['codec_name']:5s} {st['width']}x{st['height']} "
              f"{st['r_frame_rate']:>5s} {st['nb_read_frames']:>5s} frames "
              f"{os.path.getsize(path) / 1e6:6.1f} MB {'ok' if good else 'BAD TAGS/LOOP'}{note}")
    return ok


def main():
    svgs = sorted(glob.glob(os.path.join(THEME, "*", "contents", "images", "1920x1080.svg")) +
                  glob.glob(os.path.join(THEME, "*", "contents", "images", "1080x2160.svg")) +
                  glob.glob(os.path.join(THEME, "login", "*.svg")) +
                  glob.glob(os.path.join(BUILD, "debian-installer", "*.svg")) +
                  glob.glob(os.path.join(BUILD, "banners", "*.svg")))
    missing = [label for label, _, req in RENDERERS if not available(req)]
    if missing:
        print("not installed, skipped:", ", ".join(missing))
    ok = check_svgs(svgs)
    print()
    ok &= check_hdr()
    if glob.glob(os.path.join(ROOT, "media", "*.mp4")):
        print()
        ok &= check_videos()
    print("\nall checks passed" if ok else "\nSOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
