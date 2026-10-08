# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0
"""Image encoders: SDR PNG, HDR PNG (PQ + cICP), float masters, HDR codecs."""

import io
import shutil
import struct
import subprocess
import zlib

import numpy as np
from PIL import Image, PngImagePlugin

# SDR reference white in HDR encodings (ITU-R BT.2408)
REFERENCE_WHITE_NITS = 203.0

BT709_TO_BT2020 = np.array([
    [0.627403896, 0.329283039, 0.043313065],
    [0.069097289, 0.919540395, 0.011362316],
    [0.016391439, 0.088013308, 0.895595253]])


def dither_quantize(srgb, bits=8, seed=0):
    """Quantise [0,1] floats with triangular dither (no banding)."""
    rng = np.random.default_rng(seed)
    top = (1 << bits) - 1
    noise = rng.random(srgb.shape, dtype=np.float32) - rng.random(srgb.shape, dtype=np.float32)
    q = np.round(srgb * top + noise)
    return np.clip(q, 0, top).astype(np.uint8 if bits <= 8 else np.uint16)


def save_sdr_png(path, srgb, bits=8):
    if bits == 8:
        info = PngImagePlugin.PngInfo()
        info.add(b"sRGB", b"\x00")          # perceptual rendering intent
        Image.fromarray(dither_quantize(srgb, 8)).save(path, pnginfo=info,
                                                       compress_level=9)
    else:
        write_png16(path, dither_quantize(srgb, 16), [(b"sRGB", b"\x00")])


def png_bytes(srgb):
    img = np.clip(np.round(srgb * 255), 0, 255).astype(np.uint8)
    bio = io.BytesIO()
    Image.fromarray(img).save(bio, "PNG", optimize=True)
    return bio.getvalue()


# -- HDR -------------------------------------------------------------------

def pq_encode(nits):
    y = np.clip(nits / 10000.0, 0, 1)
    m1, m2 = 2610 / 16384, 2523 / 4096 * 128
    c1, c2, c3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
    ym = np.power(y, m1)
    return np.power((c1 + c2 * ym) / (1 + c3 * ym), m2)


# highlights above this share of the mastering peak roll off toward it
# instead of clipping; the stills stay below it and are left untouched
ROLLOFF_START = 0.75


def _shoulder(lin2020, peak_nits):
    """Hue-preserving roll-off of linear BT.2020 light toward peak_nits.

    Judged on each pixel's largest component, as MaxCLL is.  A tanh joins
    the identity with matching slope, so bright highlights keep their shape
    instead of flattening at a hard clip.
    """
    m = np.clip(lin2020, 0, None).max(axis=-1) * REFERENCE_WHITE_NITS
    k = ROLLOFF_START * peak_nits
    over = m > k
    if not over.any():
        return lin2020
    span = peak_nits - k
    scale = np.ones_like(m)
    scale[over] = (k + span * np.tanh((m[over] - k) / span)) / m[over]
    return lin2020 * scale[..., None]


def hdr_to_pq(lin709, peak_nits=1000.0):
    """Linear Rec.709 (1.0 = reference white) -> PQ-encoded BT.2020 [0,1]."""
    lin2020 = _shoulder(np.einsum("...c,dc->...d", lin709, BT709_TO_BT2020), peak_nits)
    nits = np.clip(lin2020, 0, None) * REFERENCE_WHITE_NITS
    return pq_encode(np.minimum(nits, peak_nits)).astype(np.float32)


def light_levels(lin709, peak_nits=None):
    """(MaxCLL, MaxFALL) in cd/m2, per CTA-861.3 (max component per pixel),
    of the light as hdr_to_pq encodes it for a peak_nits display."""
    lin2020 = np.einsum("...c,dc->...d", lin709, BT709_TO_BT2020)
    if peak_nits:
        lin2020 = _shoulder(lin2020, peak_nits)
    m = np.clip(lin2020, 0, None).max(axis=-1) * REFERENCE_WHITE_NITS
    if peak_nits:
        m = np.minimum(m, peak_nits)
    return float(m.max()), float(m.mean())


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png16(path, rgb16, extra_chunks=()):
    """16-bit RGB PNG with arbitrary ancillary chunks placed before IDAT."""
    H, W, _ = rgb16.shape
    be = rgb16.astype(">u2").view(np.uint8).reshape(H, W * 6)
    # PNG "Up" filter on every row but the first: good for smooth images
    filt = np.empty_like(be)
    filt[0] = be[0]
    filt[1:] = (be[1:].astype(np.int16) - be[:-1]).astype(np.uint8)
    ftype = np.full((H, 1), 2, dtype=np.uint8)
    ftype[0] = 0
    raw = np.hstack([ftype, filt]).tobytes()
    out = [b"\x89PNG\r\n\x1a\n",
           _chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 16, 2, 0, 0, 0))]
    out += [_chunk(tag, data) for tag, data in extra_chunks]
    out.append(_chunk(b"IDAT", zlib.compress(raw, 9)))
    out.append(_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(b"".join(out))


def hdr_png_chunks(maxcll, maxfall, peak_nits=1000.0):
    cicp = bytes([9, 16, 0, 1])      # BT.2020 primaries, PQ, RGB, full range
    # mastering display: BT.2020 primaries, D65, peak_nits / 0.0001 nits
    xy = [(0.708, 0.292), (0.170, 0.797), (0.131, 0.046)]
    mdcv = b"".join(struct.pack(">HH", round(x / 0.00002), round(y / 0.00002))
                    for x, y in xy)
    mdcv += struct.pack(">HH", round(0.3127 / 0.00002), round(0.3290 / 0.00002))
    mdcv += struct.pack(">II", round(peak_nits * 10000), 1)
    clli = struct.pack(">II", round(maxcll * 10000), round(maxfall * 10000))
    return [(b"cICP", cicp), (b"mDCv", mdcv), (b"cLLi", clli)]


def save_hdr_png(path, lin709, peak_nits=1000.0):
    pq = hdr_to_pq(lin709, peak_nits)
    maxcll, maxfall = light_levels(lin709, peak_nits)
    write_png16(path, dither_quantize(pq, 16),
                hdr_png_chunks(maxcll, maxfall, peak_nits))
    return maxcll, maxfall


def save_exr(path, lin709):
    """Scene-linear Rec.709 master (1.0 = SDR reference white), half float.

    Written with OpenImageIO (Debian: python3-openimageio); ImageMagick's
    non-HDRI build would clamp every highlight to 1.0.
    """
    import OpenImageIO as oiio
    H, W, _ = lin709.shape
    spec = oiio.ImageSpec(W, H, 3, "half")
    spec.attribute("compression", "zip")
    spec.attribute("chromaticities", "float[8]",
                   (0.64, 0.33, 0.30, 0.60, 0.15, 0.06, 0.3127, 0.3290))
    spec.attribute("whiteLuminance", REFERENCE_WHITE_NITS)
    spec.attribute("oiio:ColorSpace", "lin_rec709")
    out = oiio.ImageOutput.create(path)
    if out is None or not out.open(path, spec):
        raise RuntimeError(f"cannot write {path}: {oiio.geterror()}")
    out.write_image(np.ascontiguousarray(lin709, dtype=np.float32))
    out.close()


def have_module(name):
    import importlib.util
    return importlib.util.find_spec(name) is not None


# -- external HDR codecs (Debian: libavif-bin, libjxl-tools) -----------------

def have(tool):
    return shutil.which(tool) is not None


def avif_pq(src_png, dst, maxcll, maxfall, quality=90, speed=6):
    """HDR-only AVIF: 12-bit 4:4:4, BT.2020 primaries, PQ, full range."""
    subprocess.run(["avifenc", "--depth", "12", "--yuv", "444", "--cicp", "9/16/9",
                    "--range", "full", "--ignore-profile", "-q", str(quality),
                    "--speed", str(speed), "--clli", f"{round(maxcll)},{round(maxfall)}",
                    src_png, dst], check=True, stdout=subprocess.DEVNULL)


def avif_gainmap(sdr_png, hdr_png, dst, maxcll, maxfall, quality=90, speed=6):
    """One file for every screen: SDR base image + HDR gain map (ISO 21496-1).

    Viewers without gain-map support show the (10-bit sRGB) base; HDR
    displays apply the gain map to reach the PQ alternate image.
    """
    subprocess.run(["avifgainmaputil", "combine", sdr_png, hdr_png, dst,
                    "--cicp-base", "1/13/6", "--cicp-alternate", "9/16/9",
                    "--clli-alternate", f"{round(maxcll)},{round(maxfall)}",
                    "-q", str(quality), "--qgain-map", str(quality),
                    "-d", "10", "-y", "444", "-s", str(speed)],
                   check=True, stdout=subprocess.DEVNULL)


def jxl_pq(src_png, dst, distance=0.6, peak_nits=1000.0):
    """JPEG XL, BT.2020 PQ (colour encoding set explicitly), 16-bit input."""
    subprocess.run(["cjxl", src_png, dst, "-d", str(distance), "-e", "7",
                    "-x", "color_space=RGB_D65_202_Rel_PeQ",
                    f"--intensity_target={peak_nits:g}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
