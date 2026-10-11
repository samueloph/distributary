# Distributary

*An artwork proposal for Debian 14 "forky". One river, many forks.*

![Distributary, dusk](https://samueloph.dev/personal_website_files/debian-14-artwork/img/hero-dusk.jpg)

- **Source:** <https://salsa.debian.org/samueloph/distributary>
  (mirror: <https://github.com/samueloph/distributary>)
- **Showcase:** <https://samueloph.dev/debian-14-artwork/>, with every colour
  option, a live palette editor and wallpapers to download

## Made by a program, free as Debian

Nothing in this theme was drawn by hand, painted, photographed or produced by
an image-generating model. Every wallpaper, login screen, boot splash frame,
GRUB background, installer banner, HDR master and video comes out of the
Python program in this repository. The only outside material it uses is the
Debian logo, plus the letter shapes of Lato for the "14 · FORKY" lettering.

- **The program is the source.** What you would edit to change the artwork is
  `src/distributary/design.py` (the river's seed and shape, both palettes)
  and the rest of the generator: the preferred form for making modifications,
  as the DFSG asks of source code. The pictures are build products, like
  binaries.
- **DFSG-free.** The artwork and the program are GPL-2.0-or-later or
  CC-BY-SA-4.0, at your option: the terms desktop-base already uses for
  Ceratopsian, Debian 13's theme. The Debian Open Use Logo is LGPL-3+ or CC-BY-SA-3.0, and the
  "14 · FORKY" lettering is made of Lato outlines (SIL OFL 1.1). All of it
  fits Debian main; see [`copyright`](copyright).
- **Built from Debian alone.** Every tool and library it needs is packaged in
  Debian, with nothing downloaded at build time.
- **Reproducible.** The river grows from a fixed seed and nothing reads the
  clock, so the same source gives byte-identical files.
- **Checked.** `make check` renders every shipped SVG with librsvg, Qt SVG,
  resvg and Inkscape and compares them, and verifies the HDR signalling of
  every HDR file and the tags of every video.

### Build it yourself

```sh
sudo apt install python3-numpy python3-scipy python3-cairo python3-gi \
    gir1.2-rsvg-2.0 python3-pil python3-contourpy python3-fonttools fonts-lato
sudo apt install libavif-bin libjxl-tools python3-openimageio   # HDR files
sudo apt install ffmpeg                                          # videos
sudo apt install python3-pyqt6.qtsvg resvg inkscape             # make check

git clone https://salsa.debian.org/samueloph/distributary.git
cd distributary
./build.py --draft all     # the whole theme up to 4K, in a few minutes
make check                 # four SVG renderers agree, HDR is signalled right
```

The theme lands in `build/distributary-theme/`, laid out like
`/usr/share/desktop-base/<theme>-theme/`. `./build.py all` adds the 5K and
8K renders; [Building](#building) has the rest. To make your own colours, try
the palette editor on the showcase page, or edit a palette in
`src/distributary/design.py` and build again.

## Concept

In hydrology, a **distributary** is a channel that forks away from a river and
flows on toward the sea. It is the opposite of a tributary. Debian is the river
most of the Linux world branches from: Ubuntu, Mint, Raspberry Pi OS, Kali,
Tails and hundreds of other distributions started as forks of Debian. So for
*forky* this theme celebrates the fork itself: a single stream splits, then
splits again, into a luminous delta at dusk.

- Every junction is a Y, so there are forks everywhere. No cutlery, no
  character.
- The light sits on the first fork. The water is white where the river
  splits, then turns Debian's rose, magenta and violet as the delta spreads,
  so the Y of *forky* is the brightest point in the picture.
- Faint contour lines turn the land between the channels into islands, like a
  map.
- The fork sits on the left third line, where the eye lands first. The corners
  on the left stay calm for icons and windows, and the fine detail fades out
  to the right.

**Dusk** (dark) is the default. **Dawn** is its light counterpart, for GNOME's
light/dark wallpaper switching and for KDE colour schemes.

![Distributary, dawn](https://samueloph.dev/personal_website_files/debian-14-artwork/img/hero-dawn.jpg)

## Process

The river is not drawn by hand. It is grown by a small program following the
rules of real deltas:

- channels meander;
- they steer away from each other;
- they split with flow conserved (Murray's law, so widths add up the way real
  rivers do);
- a channel that runs into another thins out and ends, like a silted-up
  side arm.

The main stem and the first two forks are art-directed: drawn as a spline and
forced in `design.py`. Everything downstream grows from a fixed seed (6).
Contour lines are traced around the channels, and the light, glow and colours
are computed per pixel in linear light, then tone-mapped for SDR or kept for
HDR.

## Deliverables

`./build.py all` writes everything to `build/`:

| Component | Where | Notes |
|---|---|---|
| Wallpaper, dusk (default) | `distributary-theme/wallpaper/` | SVG for 5:4, 4:3, 16:10, 16:9, 21:9 and 1:2 portrait; 4K nominal sizes too. KDE `metadata.json`, GNOME `gnome-background.xml`. |
| Wallpaper, dawn (light) | `distributary-theme/wallpaper-dawn/` | Same geometry, light palette. |
| Light/dark pairing | `distributary-theme/wallpaper-adaptive/`, `gnome-background-properties/distributary.xml` | Dawn in light styles, Dusk in dark ones. KDE uses `images`/`images_dark` (symlinks); GNOME uses `filename-dark`. |
| Lock screen | `distributary-theme/lockscreen/` | Uses the wallpaper images, as Debian 13's theme does. |
| Login | `distributary-theme/login/background{,-nologo}.svg` | 1920×1200; lockup at the top centre. |
| GRUB | `distributary-theme/grub/grub-{4x3,16x9}.png` | Darkened toward the menu area so white text stays readable. |
| Plymouth | `distributary-theme/plymouth/` | Script theme. The river grows from its source and forks with boot progress. 1.5 MB. |
| Installer | `debian-installer/logo_installer{,_dark}.png`, `splash.{svg,png}` | 800×75 banner, light and dark; 640×480 boot menu splash. |
| Banners | `banners/` | Website (800×119) and wiki (380×380) banners with a "14 · FORKY" descriptor, SVG plus 2× PNG. |
| High-resolution wallpapers | `wallpapers/` | One native render per screen shape: 16:9 (4K, 5K, 8K), 16:10, 3:2, MacBook Air, 4:3, 5:4, three ultrawides, 32:9 and three phone shapes; dithered PNG. |
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
  two are identical except in the highlights, which reach about 620 cd/m²
  (MaxCLL ≈ 621, MaxFALL ≈ 15).

The HDR formats are:

- **Gain-map AVIF**: SDR base plus ISO 21496-1 gain map, one file that looks
  right on any screen.
- **PQ / BT.2020 AVIF**, 12-bit.
- **PQ / BT.2020 JPEG XL**.
- **16-bit PNG** with `cICP`, `mDCv` and `cLLi` chunks (PNG third edition).
- **Scene-linear half-float OpenEXR** master.

## Motion

`./build.py video` (or `make video`) renders these into `media/` (a colour
option's go next to its pictures, in `website/schemes/KEY/media/`):

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
  `VIDEOS="flow-dusk flow-dawn" ./build.py video`.

## Website

`website/index.html` is a showcase page for the proposal. It covers:

- the Dusk and Dawn hero (the Dusk image is the HDR gain-map AVIF), with a
  switch that re-themes the whole page;
- the boot splash, mock-ups on GNOME, Plasma, GDM, GRUB and the installer;
- the animations, every screen shape, 1:1 crops from the 8K render, and an
  HDR luminance map with measured statistics;
- a download picker: Dusk or Dawn at 43 common screen sizes (16:9 from
  720p to 8K, 16:10 including 2880×1800, 3:2 laptops, MacBook Air, 4:3, 5:4,
  ultrawide, 32:9 and phones), plus the SVG and the HDR file;
- previews of alternative colour schemes (`src/distributary/options.py`),
  each in dark and light.

A **Colours** switcher at the top shows the whole page in any colour option:
every picture and video, the page's own colours, the legend, the HDR figures
and the downloads. The page opens in Forest.

The page and the editor are kept here as source; their pictures, videos and
data are generated, so build them before opening the page:

```sh
./build.py all video website downloads editor   # the default colours
for k in midnight red teal glacier long-fade forest silt; do
    ./build.py --scheme $k all video website downloads
done
./build.py switcher        # what the page needs to know about the options
```

That is a few hours of rendering (each option goes to `website/schemes/KEY/`,
its downloads to `build/downloads/KEY/`). Then open `website/index.html`
straight from disk, or copy the whole site, videos and downloads included, into
a static web site:

```sh
make export-site DEST=/path/to/site/debian-14-artwork
```

### Palette editor

`website/editor/` (a page of the showcase) redraws the wallpaper in the browser
with WebGL while you change its colours, at the screen size you choose. It ports the renderer's formulas (water by distance from
the light, glow, core light, contour rings, the tone curve, colour along the
river), and its pictures match the Python renders to within half a level of
8-bit sRGB on average, in Chromium and in Firefox. The river's shape is fixed:
`./build.py editor` exports it once (seed 6) with the colour options as
presets.

"Randomize colours" and "Randomize parameters" draw new palettes. The editor
gives a palette as JSON, which builds into the whole theme:

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
the shipped SVG differs from the float render by 0.14/255 on average.

## Building

Everything needed is packaged in Debian (see [Build it
yourself](#build-it-yourself)); the HDR encoders are optional, and the build
skips formats whose tool is missing.

```sh
make            # or: ./build.py all
make svg        # just the desktop-base SVGs (about 20 s)
```

Targets: `svg raster hdr grub plymouth installer banners previews` (together,
`all`), plus `video`, `website`, `downloads`, `editor` and `switcher`, which
`all` leaves out.

Options:

- `--draft` stops at 4K and skips the videos, which is enough to choose
  between designs.
- `--scheme NAME` builds a colour option from `options.py` into
  `build/schemes/NAME/`, and its pictures for the showcase into
  `website/schemes/NAME/`.
- `--palette FILE` builds a palette saved from the editor, into
  `build/schemes/<its name>/` and `sites/<its name>/`.
- `--seed N` grows another river. The proposal, its previews and the editor
  use seed 6; other seeds build into their own directories.

`make check` renders every shipped SVG with librsvg (GNOME, Xfce), Qt SVG
(KDE, SDDM), resvg and Inkscape and compares them. It also confirms the HDR
signalling of every AVIF and JPEG XL file, and each video's colour tags, HDR10
metadata and seamless loop. All four renderers currently agree to within one
level on average. Side-by-side renders go to `build/check/`.

## Changing the design

`src/distributary/design.py` holds everything that defines the artwork: the
seed, the drawn main stem, the first forks and both palettes. Change a value,
rebuild, and every wallpaper, boot screen and HDR master follows.

| File | Role |
|---|---|
| `network.py` | Grows the river (meander, avoidance, forks, dead-end side arms). |
| `contours.py` | Bank contour lines, in world space. |
| `scene.py` | Linear-light land, water and glow. |
| `svgout.py` | The SVG writer. |
| `render.py` | Composites SVG over the float base, for SDR and HDR. |
| `encode.py` | PNG, PQ PNG, EXR, AVIF and JXL encoders. |
| `components.py` | GRUB, Plymouth and installer assets. |
| `logo.py` | The Debian logo, split into swirl and wordmark, and the lettering next to it. |
| `animate.py`, `videos.py` | Boot splash and growth simulations, video encoding. |
| `mockups.py` | The desktop, login and installer mock-ups on the showcase. |
| `options.py` | Alternative colour schemes, previewed on the website and offered as editor presets. |

## Trying it on a Debian system

```sh
# boot splash
sudo cp -r build/distributary-theme/plymouth /usr/share/plymouth/themes/distributary
sudo plymouth-set-default-theme -R distributary
# preview without rebooting (from a text console):
sudo plymouthd; sudo plymouth --show-splash; sleep 8; sudo plymouth quit

# wallpaper, lock screen, login, GRUB: install the theme tree next to the others
sudo cp -r build/distributary-theme /usr/share/desktop-base/
```

## License

Everything here is DFSG-free:

- **Artwork and code:** GPL-2.0-or-later or CC-BY-SA-4.0, at your option (the
  same terms as Ceratopsian, Debian 13's theme). The generated files fall
  under the same terms.
- **Debian Open Use Logo:** © Software in the Public Interest, Inc., LGPL-3+ or
  CC-BY-SA-3.0.
- **The "14 · FORKY" lettering:** glyph outlines from Lato (SIL OFL 1.1).
- **Plymouth script:** its message, passphrase and fsck handling is
  adapted from the boot splash of Ceratopsian (Debian 13's theme), desktop-base's
  `ceratopsian.script`
  (GPL-2+).

See [`COPYING`](COPYING) and the machine-readable [`copyright`](copyright).
