# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""The theme in context: desktops, login, installer and HDR views.

Drawn for the showcase website.  UI chrome is drawn at 2x and scaled down,
so edges and text are anti-aliased; the wallpapers underneath come straight
from the build.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FA = "/usr/share/fonts/truetype/font-awesome"
ADWAITA = "/usr/share/fonts/truetype/adwaita/AdwaitaSans-Regular.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NOTO = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"   # Plasma's font, if present

# Font Awesome 6 code points
ICON = {"wifi": "", "volume": "", "battery": "", "power": "",
        "user": "", "folder": "", "terminal": "", "gear": "",
        "bag": "", "bell": "", "clipboard": "", "up": "",
        "arrow": "", "firefox": "", "a11y": "", "chevron-down": ""}

S = 2      # supersampling factor for UI layers


def font(path, size, weight=None):
    f = ImageFont.truetype(path, round(size * S))
    if weight:
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
    return f


def ui_font(size, weight=None):
    return font(ADWAITA, size, weight)


def icon_font(size, brands=False):
    # Debian ships Font Awesome under versioned names: take the newest
    import glob
    import re
    kind = "brands-400" if brands else "solid-900"
    found = glob.glob(os.path.join(FA, f"fa-*-{kind}.ttf"))
    if not found:
        raise SystemExit(f"Font Awesome not found in {FA}: sudo apt install fonts-font-awesome-legacy")
    newest = max(found, key=lambda p: [int(n) for n in re.findall(r"\d+", os.path.basename(p))[:3]])
    return font(newest, size)


class Layer:
    """A transparent 2x canvas for UI chrome, composited onto a 1x image."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def rect(self, box, radius=0, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = (v * S for v in box)
        self.d.rounded_rectangle((x0, y0, x1, y1), radius=radius * S, fill=fill,
                                 outline=outline, width=max(1, round(width * S)))

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(tuple(v * S for v in box), fill=fill, outline=outline,
                       width=max(1, round(width * S)))

    def text(self, xy, s, fnt, fill, anchor="la"):
        self.d.text((xy[0] * S, xy[1] * S), s, font=fnt, fill=fill, anchor=anchor)

    def length(self, s, fnt):
        return self.d.textlength(s, font=fnt) / S

    def paste(self, im, xy):
        im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
        self.img.alpha_composite(im.convert("RGBA"), (round(xy[0] * S), round(xy[1] * S)))

    def over(self, base):
        small = self.img.resize((self.W, self.H), Image.LANCZOS)
        out = base.convert("RGBA")
        out.alpha_composite(small)
        return out.convert("RGB")


def shadow(base, box, radius=12, blur=28, opacity=0.45, offset=(0, 10)):
    """Soft drop shadow under a window."""
    W, H = base.size
    m = Image.new("L", (W, H), 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(m).rounded_rectangle((x0 + offset[0], y0 + offset[1], x1 + offset[0],
                                         y1 + offset[1]), radius=radius, fill=int(255 * opacity))
    m = m.filter(ImageFilter.GaussianBlur(blur))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, base, m)


# -- GNOME -------------------------------------------------------------------------

def gnome_topbar(L, W, clock="Sat 26 Sep  19:40"):
    L.rect((0, 0, W, 32), fill=(0, 0, 0, 255))
    # workspace indicator: active pill + two dots
    L.rect((16, 12, 46, 20), radius=4, fill=(255, 255, 255, 255))
    for i in range(2):
        L.ellipse((54 + i * 14, 12, 62 + i * 14, 20), fill=(255, 255, 255, 110))
    f = ui_font(15, "Bold")
    L.text((W / 2, 16.5), clock, f, (255, 255, 255, 255), anchor="mm")
    fi = icon_font(14)
    x = W - 26
    for name in ("power", "battery", "volume", "wifi"):
        L.text((x, 16.5), ICON[name], fi, (255, 255, 255, 235), anchor="mm")
        x -= 30 if name != "power" else 34


def gnome(wallpaper, terminal=False):
    """GNOME Shell: the top bar, optionally a terminal on the calm ground at
    the top left, clear of the river."""
    base = wallpaper.convert("RGB")
    W, H = base.size
    box = (100, 88, 790, 410)
    if terminal:
        base = shadow(base, box, radius=12)
    L = Layer(W, H)
    gnome_topbar(L, W)
    if terminal:
        x0, y0, x1, y1 = box
        L.rect(box, radius=12, fill=(30, 30, 33, 255))
        L.rect((x0, y0, x1, y0 + 46), radius=12, fill=(46, 46, 50, 255))
        L.rect((x0, y0 + 30, x1, y0 + 46), fill=(46, 46, 50, 255))
        L.rect((x0, y0 + 46, x1, y0 + 47), fill=(0, 0, 0, 120))
        L.text(((x0 + x1) / 2, y0 + 23), "debian@forky: ~", ui_font(14, "Bold"),
               (255, 255, 255, 235), anchor="mm")
        L.ellipse((x1 - 36, y0 + 11, x1 - 12, y0 + 35), fill=(255, 255, 255, 28))
        L.text((x1 - 24, y0 + 23), "×", ui_font(17), (255, 255, 255, 230), anchor="mm")
        m, mb = font(MONO, 14.5), font(MONO_BOLD, 14.5)
        green, blue, fg = (138, 226, 52, 255), (114, 159, 207, 255), (225, 225, 228, 255)
        lines = [
            [("debian@forky", green, mb), (":", fg, m), ("~", blue, mb), ("$ cat /etc/debian_version", fg, m)],
            [("forky/sid", fg, m)],
            [("debian@forky", green, mb), (":", fg, m), ("~", blue, mb), ("$ ls /usr/share/desktop-base/distributary-theme", fg, m)],
            [("gnome-background-properties  lockscreen  plymouth   wallpaper-adaptive", blue, mb)],
            [("grub                         login       wallpaper  wallpaper-light", blue, mb)],
            [("debian@forky", green, mb), (":", fg, m), ("~", blue, mb), ("$ ", fg, m), ("█", fg, m)],
        ]
        y = y0 + 66
        for parts in lines:
            x = x0 + 18
            for s, col, fnt in parts:
                L.text((x, y), s, fnt, col)
                x += L.length(s, fnt)
            y += 24
    return L.over(base)


# -- KDE Plasma -------------------------------------------------------------------------

def plasma(wallpaper, swirl):
    """Plasma 6: floating panel with launcher, pinned apps, tray and clock."""
    base = wallpaper.convert("RGB")
    W, H = base.size
    box = (8, H - 52, W - 8, H - 8)
    # the panel blurs what lies behind it
    x0, y0, x1, y1 = box
    region = base.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(18))
    base.paste(region, (x0, y0))
    L = Layer(W, H)
    L.rect(box, radius=10, fill=(32, 35, 40, 222), outline=(255, 255, 255, 24), width=1)
    cy = (y0 + y1) / 2
    sw = swirl.resize((round(swirl.width * 26 / swirl.height), 26), Image.LANCZOS)
    L.paste(sw, (x0 + 14, cy - 13))
    apps = [("firefox", (255, 125, 0, 255), True), ("folder", (29, 153, 243, 255), False),
            ("terminal", (160, 160, 168, 255), False), ("bag", (61, 174, 233, 255), False),
            ("gear", (180, 180, 190, 255), False)]
    x = x0 + 64
    for i, (name, col, brand) in enumerate(apps):
        L.rect((x - 2, cy - 18, x + 38, cy + 18), radius=6,
               fill=(255, 255, 255, 30) if i == 1 else None)
        L.text((x + 18, cy), ICON[name], icon_font(22, brands=brand), col, anchor="mm")
        if i in (0, 1):
            L.rect((x + 10, y1 - 5, x + 26, y1 - 3), radius=1, fill=(61, 174, 233, 255))
        x += 46
    fc = font(NOTO if os.path.exists(NOTO) else ADWAITA, 13)
    L.text((x1 - 60, cy - 8), "19:40", fc, (252, 252, 252, 255), anchor="mm")
    L.text((x1 - 60, cy + 9), "26/09/2026", font(NOTO if os.path.exists(NOTO) else ADWAITA, 10.5),
           (220, 220, 225, 230), anchor="mm")
    fi = icon_font(14)
    xi = x1 - 128
    for name in ("battery", "wifi", "volume", "bell", "clipboard", "up"):
        L.text((xi, cy), ICON[name], fi, (235, 235, 240, 225), anchor="mm")
        xi -= 30
    L.rect((x1 - 12, y0 + 10, x1 - 8, y1 - 10), radius=1, fill=(255, 255, 255, 40))
    return L.over(base)


# -- login -------------------------------------------------------------------------------

def gdm(background, light=False):
    """GDM's greeter over the login background: top bar and a user card, in
    dark ink over the light background."""
    base = background.convert("RGB")
    W, H = base.size
    L = Layer(W, H)
    gnome_topbar(L, W, clock="Sat 26 Sep  19:38")
    ink = (36, 36, 40) if light else (255, 255, 255)
    cx, cy = W / 2, H * 0.47
    L.ellipse((cx - 48, cy - 48, cx + 48, cy + 48), fill=(94, 92, 100, 255))
    L.text((cx, cy + 4), ICON["user"], icon_font(44), (222, 221, 226, 255), anchor="mm")
    L.text((cx, cy + 78), "Debian User", ui_font(20, "SemiBold"), (*ink, 255), anchor="mm")
    ex0, ey0 = cx - 160, cy + 108
    L.rect((ex0, ey0, ex0 + 320, ey0 + 40), radius=20, fill=(*ink, 38),
           outline=(*ink, 50), width=1)
    L.text((ex0 + 20, ey0 + 20), "Password", ui_font(15), (*ink, 140), anchor="lm")
    L.ellipse((ex0 + 336, ey0 + 2, ex0 + 372, ey0 + 38), fill=(*ink, 38))
    L.text((ex0 + 354, ey0 + 20), ICON["arrow"], icon_font(14), (*ink, 210), anchor="mm")
    return L.over(base)


# -- debian-installer --------------------------------------------------------------------

LANGUAGES = ["Català", "Čeština", "Dansk", "Deutsch", "English", "Español", "Esperanto",
             "Euskara", "Français", "Galego", "Italiano", "Nederlands", "Português",
             "Português do Brasil", "Suomi"]


def installer(banner, dark=False, scale=2):
    """d-i's graphical "Select a language" screen with the banner (800x600)."""
    W, H = 800, 600
    k = scale
    if dark:
        bg, panel, fg, sub, box_bg, sel, sel_fg, btn = ((49, 49, 51), (38, 38, 40), (236, 236, 238),
                                                         (200, 200, 205), (30, 30, 32), (53, 132, 228),
                                                         (255, 255, 255), (58, 58, 62))
    else:
        bg, panel, fg, sub, box_bg, sel, sel_fg, btn = ((246, 245, 244), (232, 232, 231), (46, 52, 54),
                                                         (60, 64, 66), (255, 255, 255), (53, 132, 228),
                                                         (255, 255, 255), (250, 250, 250))
    img = Image.new("RGB", (W * k, H * k), bg)
    img.paste(banner.convert("RGB").resize((W * k, 75 * k), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(img)
    fb, fr = ImageFont.truetype(DEJAVU_BOLD, 15 * k), ImageFont.truetype(DEJAVU, 13 * k)
    d.rectangle((0, 75 * k, W * k, 106 * k), fill=panel)
    d.text((12 * k, 91 * k), "Select a language", font=fb, fill=fg, anchor="lm")
    d.text((12 * k, 118 * k), "Choose the language to be used for the installation process.",
           font=fr, fill=sub)
    lb = (12 * k, 142 * k, (W - 12) * k, 540 * k)
    d.rectangle(lb, fill=box_bg, outline=(160, 160, 160) if not dark else (80, 80, 84), width=k)
    y = 150 * k
    for lang in LANGUAGES:
        if lang == "English":
            d.rectangle((lb[0] + k, y - 4 * k, lb[2] - k, y + 18 * k), fill=sel)
        d.text((24 * k, y), lang, font=fr, fill=sel_fg if lang == "English" else fg)
        y += 26 * k
        if y > 525 * k:
            break
    for label, x0 in (("Screenshot", 12), ("Go Back", 606), ("Continue", 704)):
        w = 90 if label != "Screenshot" else 96
        d.rounded_rectangle((x0 * k, 552 * k, (x0 + w) * k, 584 * k), radius=4 * k, fill=btn,
                            outline=(170, 170, 170) if not dark else (90, 90, 94), width=k)
        d.text(((x0 + w / 2) * k, 568 * k), label, font=fr, fill=fg, anchor="mm")
    return img


# -- HDR -----------------------------------------------------------------------------------

def luminance_map(hdr_lin, lo=6.0, hi=1000.0, white=203.0):
    """False-colour luminance (log scale, inferno) of a linear HDR image."""
    from matplotlib import colormaps
    Y = np.maximum(hdr_lin @ np.array([0.2126, 0.7152, 0.0722], np.float32) * white, 1e-3)
    t = np.clip((np.log10(Y) - np.log10(lo)) / (np.log10(hi) - np.log10(lo)), 0, 1)
    rgb = colormaps["inferno"](t)[..., :3]
    return Image.fromarray(np.round(rgb * 255).astype(np.uint8)), Y


def hdr_stats(Y, maxcll, headroom):
    return {"peak (MaxCLL)": f"{maxcll:.0f} nits",
            "frame average": f"{Y.mean():.0f} nits",
            "median pixel": f"{np.median(Y):.0f} nits",
            "above SDR white": f"{(Y > 203).mean() * 100:.1f} %",
            "above 400 nits": f"{(Y > 400).mean() * 100:.2f} %",
            "gain map headroom": f"{headroom:.2f} stops"}
