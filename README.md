# Distributary

*An artwork proposal for Debian 14 "forky". One river, many forks.*

![Distributary, dark](https://samueloph.dev/personal_website_files/debian-distributary-theme/img/hero-dark.jpg)

- **Source:** <https://salsa.debian.org/samueloph/distributary> and
  <https://github.com/samueloph/distributary>
- **Showcase:** <https://samueloph.dev/debian-distributary-theme/>, with every colour
  option, a live palette editor and wallpapers to download

## Made by a program, free as Debian

Nothing in this theme was drawn by hand, painted, photographed or produced by
an image-generating model. Every wallpaper, login screen, boot splash frame,
GRUB background, installer banner, HDR master and video comes out of the
Python program in this repository. The only outside material it uses is the
Debian logo, plus the letter shapes of Lato for the "14 · FORKY" lettering.

- **The program is the source.** To change the artwork you edit
  `src/distributary/design.py` (the river's seed and shape, both palettes)
  or the rest of the generator. That code is the preferred form for making
  modifications, the usual test of source code; the pictures are build
  products, like binaries.
- **DFSG-free.** The artwork and the program are GPL-2.0-or-later or
  CC-BY-SA-4.0, at your option; the GPL is what desktop-base, Ceratopsian
  included, already uses. The Debian Open Use Logo is LGPL-3+ or
  CC-BY-SA-3.0, and the "14 · FORKY" lettering is made of Lato outlines
  (SIL OFL 1.1). All of it fits Debian main; see [`copyright`](copyright).
- **Built from Debian alone.** Every tool and library it needs is packaged in
  Debian, with nothing downloaded at build time.
- **Reproducible.** The river grows from a fixed seed and nothing reads the
  clock, so the same source, built with the same tools, gives byte-identical
  files.
- **Checked.** `make check` renders the SVGs (each wallpaper at 16:9 and
  phone size, the login screens, the installer's banner and splash, and the
  banners) with librsvg, Qt SVG, resvg and Inkscape and compares them, and
  verifies the HDR signalling of the AVIF and JPEG XL files and the colour
  tags of the videos.

### Fork your own wallpaper

Start small, with one colour and just the wallpaper:

```sh
sudo apt install python3-numpy python3-scipy python3-cairo python3-gi \
    gir1.2-rsvg-2.0 python3-pil python3-contourpy python3-fonttools fonts-lato

git clone https://salsa.debian.org/samueloph/distributary.git
# or: git clone https://github.com/samueloph/distributary.git
cd distributary
./build.py svg                     # Forest, the default, as SVGs, in under a minute
SIZES=1920x1080 ./build.py raster  # and PNGs, dark and light, at your screen's size
```

The SVGs land in `build/distributary-theme/wallpaper/contents/images/`
(dark) and `wallpaper-light/contents/images/`, the PNGs in
`build/wallpapers/`. From there:

- **Another colour:** `--scheme` takes `violet`, `midnight`, `red`, `teal`,
  `glacier`, `lineage` or `silt` (or `forest`, the default), and builds it
  into `build/schemes/KEY/`; add `-even` (as in `forest-even`) to build any
  colour but Lineage without the accent on the fork, its brightest light (or
  darkest ink).
- **Your own colours:** make them in the
  [palette editor](https://samueloph.dev/personal_website_files/debian-distributary-theme/editor/)
  and build its JSON with `--palette my-colours.json` instead of `--scheme`,
  or edit a palette in `src/distributary/design.py`.
- **A larger Debian logo:** `--logo-scale 1.4` (or the editor's logo size
  slider).
- **The whole theme** (login, GRUB, Plymouth, installer, HDR):
  `./build.py --draft all` stops at 4K and takes 10–15 minutes; `./build.py all`
  adds the 5K and 8K renders. The HDR files need
  `sudo apt install libavif-bin libjxl-tools python3-openimageio`; formats
  whose tool is missing are skipped.
- **The videos:** `./build.py video`, with `ffmpeg`, takes about a quarter
  of an hour on a 14-core machine.
- **Checks:** `make check`, after
  `sudo apt install python3-pyqt6.qtsvg resvg inkscape`, renders the SVGs in
  four renderers and checks the HDR signalling.

The full theme lands in `build/distributary-theme/` (or
`build/schemes/KEY/distributary-theme/`), laid out like
`/usr/share/desktop-base/<theme>-theme/`; [Building](#building) has the rest.

## Concept

In hydrology, a **distributary** is a channel that forks away from a river and
flows on toward the sea. It is the opposite of a tributary. Debian is the river
much of the Linux world branches from: Ubuntu, Raspberry Pi OS, Kali, Tails
and hundreds of other distributions are built on Debian, and Mint on Ubuntu, a
fork of a fork. So for
*forky* this theme celebrates the fork itself: a single stream splits, then
splits again, into a luminous delta at dusk.

- Every junction is a Y, so there are forks everywhere: no cutlery, and no
  Forky, the Toy Story character.
- The light sits on the first fork. The water is nearly white where the
  river splits, then turns gold and sage green as the delta spreads, so the
  Y of *forky* is the brightest point in the picture.
- Faint contour lines turn the land between the channels into islands, like a
  map.
- The fork sits on the left third line, where the eye lands first. The corners
  on the left stay calm for icons and windows, and the fine detail fades out
  to the right.

The **dark** version is the default. The **light** version is its counterpart,
for GNOME's light/dark wallpaper switching and for KDE colour schemes. There
the river is ink on pale paper, and the accent on the fork is its deepest ink
instead of a light.

![Distributary, light](https://samueloph.dev/personal_website_files/debian-distributary-theme/img/hero-light.jpg)

## Process

The river is not drawn by hand. It is grown by a small program following the
rules of real deltas:

- channels meander;
- they steer away from each other;
- they split with flow conserved: the widths follow a generalised
  [Murray's law](https://en.wikipedia.org/wiki/Murray%27s_law) (exponent 2.4);
- a channel that runs into another thins out and ends, like a silted-up
  side arm.

The main stem and the first three forks are art-directed in `design.py`: the
stem is a spline through five points, and the forks have set positions,
angles and shares of the flow. Everything downstream grows from a fixed seed
(6).
Contour lines are traced around the channels, and the light, glow and colours
are computed per pixel in linear light, then tone-mapped for SDR or kept for
HDR.

## Deliverables

`./build.py all` writes everything to `build/`:

| Component | Where | Notes |
|---|---|---|
| Wallpaper, dark (default) | `distributary-theme/wallpaper/` | SVG for 5:4, 4:3, 16:10, 16:9, 21:9 and 1:2 portrait, at nominal sizes from 1280×800 to 5120×2160. KDE `metadata.json`, GNOME `gnome-background.xml`. |
| Wallpaper, light | `distributary-theme/wallpaper-light/` | Same geometry, light palette. |
| Light/dark pairing | `distributary-theme/wallpaper-adaptive/`, `distributary-theme/gnome-background-properties/distributary.xml` | The light wallpaper in light styles, the dark one in dark styles. KDE uses `images`/`images_dark` (symlinks); GNOME uses `filename-dark`. |
| Lock screen | `distributary-theme/lockscreen/` | Uses the wallpaper images, as Debian 13's theme does. |
| Login | `distributary-theme/login/background{,-nologo}.svg` | 1920×1200; lockup at the top centre. |
| GRUB | `distributary-theme/grub/grub-{4x3,16x9}.png` | Darkened toward the menu area so white text stays readable. |
| Plymouth | `distributary-theme/plymouth/` | Script theme. The river grows from its source and forks with boot progress. 1.5 MB. |
| Installer | `debian-installer/logo_installer{,_dark}.{svg,png}`, `splash.{svg,png}` | 800×75 banner, the same for the installer's light and dark themes, dark so that the white label the installer writes on it stays readable; 640×480 boot menu splash. The installer builds its PNGs from the SVGs; the PNGs here are librsvg's renders of them. |
| Banners | `banners/` | Website (800×119) and wiki (380×380) banners with a "14 · FORKY" descriptor, SVG plus 2× PNG. |
| High-resolution wallpapers | `wallpapers/` | One native render per screen shape: 16:9 (4K, 5K, 8K), 16:10, 3:2, three MacBooks (Air 13", Pro 14" and 16"), 4:3, 5:4, three ultrawides, 32:9 and three phone shapes; dithered PNG. |
| HDR | `hdr/` | See below. |

The `distributary-theme/` tree mirrors `/usr/share/desktop-base/<theme>-theme/`
so it can drop into desktop-base.

## HDR

The light on the water at the fork is brighter than white paper, which makes
this an honest HDR image rather than a stretched SDR one. The renderer works in scene-linear
light where 1.0 is SDR reference white (203 cd/m², ITU-R BT.2408):

- **SDR** uses a hue-preserving tone curve that leaves everything below the
  knee untouched. Only the highlights around the fork roll off.
- **HDR** is the SDR picture plus exactly the light the tone curve removed. The
  two are identical except in the highlights, which reach about 630 cd/m²
  (MaxCLL ≈ 631, MaxFALL ≈ 12).

The HDR formats are:

- **Gain-map AVIF**: SDR base plus ISO 21496-1 gain map, one file that looks
  right on any screen.
- **PQ / BT.2020 AVIF**, 12-bit.
- **PQ / BT.2020 JPEG XL**.
- **16-bit PNG** with `cICP`, `mDCv` and `cLLi` chunks (PNG third edition).
- **Scene-linear half-float OpenEXR** master.

## Motion

`./build.py video` (or `make video`) renders these into `media/` (a colour
option's videos go next to its pictures, in `website/schemes/KEY/media/`):

| Video | What it shows |
|---|---|
| `plymouth-boot` | The boot splash as it plays: the river grows and forks with boot progress, pauses for a disk passphrase, then hands over to the login screen. |
| `river-growth` | The delta drawing itself from its source, then holding still. |
| `boot-to-desktop` | GRUB, Plymouth, login and desktop in one take. |

- **Plymouth is really animated.** The growth is in the shipped theme, and
  the video follows the Plymouth script's own layout, crossfade and easing,
  using the theme's real images.
- **GRUB and the login screen are simulations.** Their frames reuse the
  shipped backgrounds with a drawn-in menu or fade, so treat them as
  illustrations rather than captures. GRUB itself cannot animate.
- **Formats:** 10-bit AV1, plus H.264 for older players, tagged BT.709.
- A flowing wallpaper loop (pulses of light travelling downstream, also in
  HDR10) is still in the generator but off by default:
  `VIDEOS="flow-dark flow-light" ./build.py video`.

## Website

`website/index.html` is a showcase page for the proposal. It covers:

- the dark and light hero (the dark image is the HDR gain-map AVIF), with
  two switches on it: dark or light, which re-themes the whole page, and the
  accent on the fork, on or off (on phones they sit under the picture);
- the boot splash, mock-ups on GNOME, Plasma, GDM, GRUB and the installer;
- the animations, every screen shape, 1:1 crops from the 8K render, and an
  HDR luminance map with measured statistics;
- a download picker: dark or light at 51 common screen sizes (16:9 from
  720p to 8K, 4.5K (24-inch iMac) and 6K (Pro Display XDR) included; 16:10
  including 2160×1350, 2880×1800 and 2944×1840; 3:2 laptops; MacBook Air
  and Pro; 4:3, 5:4, ultrawide, 32:9 and phones), plus the SVG and, where some light is
  brighter than white, the HDR file; the palette editor offers the same sizes;
- a gallery of every colour (`src/distributary/options.py`), with and without
  the accent on the fork, following the dark/light switch.

The **Colours** bar under the title, with the hero's accent switch, shows the
whole page in any colour, with or without the accent: every picture and
video, the page's own colours, the legend, the HDR figures and the downloads.
The accent is the light on the fork in the dark version and the deepest ink
in the light one, and the page's words and legend say which. The page opens
in Forest, the first colour in the bar; the bar's last tile opens the
palette editor. The download picker comes right after the introduction.

The page and the editor are kept here as source; their pictures, videos and
data are generated, so build them before opening the page:

```sh
./build.py all video website downloads editor   # Forest, the default
for k in violet midnight red teal glacier lineage silt; do
    ./build.py --scheme $k all video website downloads
done
for k in violet midnight red teal glacier forest silt; do   # even: without the accent on the fork
    ./build.py --scheme $k-even all video website downloads
done
./build.py switcher        # what the page needs to know about the colours
```

That is a night of rendering: each colour and version takes about half an
hour alone on a 14-core machine, or just under an hour with three side by
side (they can run together: each goes to `website/schemes/KEY/`, its
downloads to `build/downloads/KEY/`). Then open `website/index.html`
straight from disk, or publish it with `make export-site` (below).
The downloads go to a site of their own: with every colour they are 712 MB,
and a GitHub Pages site holds 1 GB.

```sh
make export-site DEST=/path/to/site/debian-distributary-theme
make export-downloads DEST=/path/to/wallpapers-site
```

The page finds its downloads through `DL_BASE` in `website/index.html`:
`/distributary-wallpapers/` on samueloph.dev and on a local server, and the
full https://samueloph.dev/distributary-wallpapers/ anywhere else, so a copy
opened from disk still downloads from samueloph.dev.

### Palette editor

`website/editor/` ("Fork your own wallpaper", a page of the showcase) redraws
the wallpaper in the browser with WebGL while you change its colours, at any of
the download sizes, phones and 32:9 included, each framed as the build frames
it (sizes above about 9.5 megapixels are drawn smaller and shown scaled). It
ports the renderer's formulas (water by distance from the light, glow, core
light, contour rings, the tone curve, colour along the river), and its
pictures match the Python renders to within half a level of 8-bit sRGB on
average, in Chromium and in Firefox. The river's shape is fixed: `./build.py
editor` exports it once (seed 6) with the colour options as presets and the
list of sizes.

Channels and contour lines take their colour as the build's SVGs do, from
gradients of 20 stops, so even a sharp turn in the colours previews as it
will build. A water colour that lies past the river's end at the size picked
is dimmed and says so: it only shows on wider screens, or with a shorter
reach.

Randomize (the die) draws new colours and parameters together. "Randomize
colours" keeps the parameters (the accent's place and reach, the glow),
"Randomize parameters" keeps the colours, and "← Previous" undoes up to the
last five. A different river needs another seed, which only the program on
your computer can grow. "Download wallpaper" saves the preview as drawn,
logo included, as `debian-distributary-theme.png`; the largest sizes come
out smaller, and the program makes them in full. The editor always opens on
Forest, like the showcase; a palette changed on the last visit waits in a
"Where you left off" tile.

The editor saves a palette as JSON, and under "Use it" it lists the
commands that build it, from installing the dependencies to the wallpaper at
the size picked. The JSON builds into the whole theme:

```sh
./build.py --palette my-colours.json --draft all website
```

## One source, SVG and raster

Each wallpaper is an SVG:

- **Vector:** the crisp parts (channels, contour lines, logo).
- **Embedded image:** the soft parts (land, haze, glow) are a small PNG, as
  Homeworld's SVGs also did.
- **No filters:** only gradients, group opacity and that image are used, so the
  files stay within what Qt SVG (KDE) supports as well as librsvg.

The high-resolution PNGs and HDR files are *the same SVG*, rendered by librsvg
(GNOME's SVG renderer) over a full-resolution floating-point base. The
desktop-base SVGs and the 8K renders cannot drift apart. Rendered at 1920×1080,
the shipped SVG differs from the float render by under 0.2/255 on average.

## Building

Everything needed is packaged in Debian (see [Fork your own
wallpaper](#fork-your-own-wallpaper)). The HDR encoders are optional for the
theme, and the build skips formats whose tool is missing; `./build.py
website` needs them, and also
`python3-matplotlib fonts-adwaita-sans fonts-font-awesome-legacy`.

```sh
make            # or: ./build.py all
make svg        # just the desktop-base SVGs (under a minute)
```

Targets: `svg raster hdr grub plymouth installer banners previews` (together,
`all`), plus `video`, `website`, `downloads`, `editor` and `switcher`, which
`all` leaves out.

Options:

- `--draft` stops at 4K and skips the videos, which is enough to choose
  between designs.
- `--scheme NAME` builds a colour from `options.py` into
  `build/schemes/NAME/`, and its pictures for the showcase into
  `website/schemes/NAME/`; `NAME-even` builds it without the accent on the
  fork.
- `--palette FILE` builds a palette saved from the editor, into
  `build/schemes/<its name>/` and `sites/<its name>/`.
- `--logo-scale K` draws the Debian logo and wordmark K times their size on
  the wallpapers and the login screen (`1.4` is 40% larger), staying in
  place: anchored at its left end on landscape wallpapers, at its centre on
  phones and the login screen. The editor's logo size slider saves it in the
  palette's JSON as `logo_scale`, and this option overrides that. 1, the
  default, is the published size.
- `--seed N` grows another river. The proposal, its previews and the editor
  use seed 6; other seeds build into their own directories.

`make check` renders the SVGs (each wallpaper at 1920×1080 and 1080×2160,
the login screens, the installer's banner and splash, and the banners) with
librsvg (GNOME, Xfce, the installer), Qt SVG (KDE, SDDM), resvg and Inkscape
and compares them. It also confirms the HDR signalling of every AVIF and
JPEG XL file, and the colour tags of each video in `media/` (for the
optional flowing loop, also its HDR10 metadata and seamless loop). All four
renderers currently agree to within one level on average. Side-by-side
renders go to `build/check/`.

## Changing the design

`src/distributary/design.py` holds everything that defines the artwork: the
seed, the main stem's course, the first forks and the palettes: Violet's,
which every colour starts from, and Forest's, the default. Change a value,
rebuild, and every wallpaper, boot screen and HDR master follows.

| File | Role |
|---|---|
| `network.py` | Grows the river (meander, avoidance, forks, dead-end side arms). |
| `contours.py` | Bank contour lines, in world space. |
| `scene.py` | Linear-light land, water and glow. |
| `raster.py` | The scene-linear rasteriser: drawing, blurs and the SDR tone curve. |
| `geometry.py` | Shared geometry: views (world to pixels) and ribbon outlines. |
| `svgout.py` | The SVG writer. |
| `render.py` | Composites SVG over the float base, for SDR and HDR. |
| `encode.py` | PNG, PQ PNG, EXR, AVIF and JXL encoders. |
| `components.py` | GRUB and Plymouth assets. |
| `logo.py` | The Debian logo, split into swirl and wordmark, and the lettering next to it. |
| `animate.py`, `videos.py` | Boot splash and growth simulations, video encoding. |
| `mockups.py` | The desktop, login and installer mock-ups on the showcase. |
| `options.py` | The colours, with and without the accent on the fork, previewed on the website and offered as editor presets. |

## Trying it on a Debian system

```sh
# boot splash
sudo cp -r build/distributary-theme/plymouth /usr/share/plymouth/themes/distributary
sudo plymouth-set-default-theme -R distributary
# preview without rebooting (from a text console):
sudo plymouthd; sudo plymouth --show-splash; sleep 8; sudo plymouth quit

# wallpaper, lock screen, login, GRUB: install the theme tree next to the
# others, then make it the active theme
sudo cp -r build/distributary-theme /usr/share/desktop-base/
sudo update-alternatives --install /usr/share/desktop-base/active-theme \
    desktop-theme /usr/share/desktop-base/distributary-theme 10
sudo update-alternatives --set desktop-theme /usr/share/desktop-base/distributary-theme
sudo update-grub
# back to the default theme: sudo update-alternatives --auto desktop-theme
```

## Related work

Rivers and their branching have been drawn before. The closest work we know
of, for comparison:

- Daniel Coe, *4K Rivers*: real rivers and deltas rendered from
  high-resolution elevation data, some in glowing channels on dark ground.
  <https://dancoecarto.com/4k-rivers>
- Robert Hodgin, *Meander* (2020): a program that grows fictional meandering
  rivers and draws them as maps. <https://roberthodgin.com/project/meander>

No picture was traced or used as input here: Distributary's river is grown
by its own program, as [Process](#process) describes.

## Licence

Everything here is DFSG-free:

- **Artwork and code:** GPL-2.0-or-later or CC-BY-SA-4.0, at your option; the
  GPL is what desktop-base, Ceratopsian included, already uses. The generated
  files fall under the same terms.
- **Debian Open Use Logo:** © Software in the Public Interest, Inc., LGPL-3+ or
  CC-BY-SA-3.0.
- **The "14 · FORKY" lettering:** glyph outlines from Lato (SIL OFL 1.1).
- **Plymouth script:** its message, passphrase and fsck handling is
  adapted from the boot splash of Ceratopsian (Debian 13's theme), desktop-base's
  `ceratopsian.script`
  (GPL-2+).

See [`COPYING`](COPYING) and the machine-readable [`copyright`](copyright).
