"""
Bitmap Heightmap Generator — MASTER (LOCKED) v3.6 DARK UI (BRANDED, DETERMINISTIC)
---------------------------------------------------------------------------------
✅ Seed: 1..2,000,000 (bitmap number) = fingerprint of terrain (deterministic)
✅ Exports ALL 47 every time (locked)
✅ 2017×2017 16-bit grayscale PNG (I;16) to heightmaps_out (or chosen folder)
✅ Mid-gray sea level (0.5), coastline shelf clamp + shelf band
✅ Fade-to-black shoreline band (34px) on ALL 4 sides
✅ Erosion + rivers + lakes + outlets + deltas + ridge preservation
✅ GUI: black background + light grey text
✅ Branding:
   - logo.png   554×150 (top)
   - qr.png     100×100 (above footer)
   - footer.png 233×100 (bottom)
✅ Preview grid: 3×3 with Prev/Next paging through all 47
✅ Thumbnails are 1/4 size (90×90) and SAVED OUT
   - Saved to: <parent_of_heightmaps_out>/thumbnails_out
     Example: if output folder is C:\X\heightmaps_out -> thumbnails saved to C:\X\thumbnails_out
✅ Preview thumbnails include OVERLAID BIOME LABELS (baked into the image)
✅ Scrollbar + resizable window
✅ NEW: “Instructions 📘” window with 2 pages + Home link (Apple-simple + emojis)

Place beside this .py:
- logo.png   (554x150)
- qr.png     (100x100) -> QR should point to https://metasoftstudios.com
- footer.png (426x100)
"""

import os
import math
import time
import zlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFont


# ----------------------------
# Biomes (47 total)
# ----------------------------
EARTH_BIOMES_44 = [
    "Oceanic Archipelago", "Temperate Island", "Tropical Island", "Arid Island",
    "Alpine Highlands", "Rolling Hills", "Coastal Plains", "River Delta",
    "Canyonlands", "Badlands", "Desert Dunes", "Desert Rock Plateau",
    "Savanna", "Steppe", "Prairie", "Mediterranean Scrub",
    "Temperate Forest", "Mixed Forest", "Old Growth Forest", "Rainforest",
    "Mangrove Coast", "Swamp", "Marshland", "Fen",
    "Tundra", "Taiga", "Boreal Wetlands", "Glacier Field",
    "Volcanic Isles", "Basalt Shelf", "Lava Plains (Dormant)", "Cratered Highlands",
    "Karst Plateau", "Limestone Ridges", "Redwood Valleys", "Fog Coast",
    "Coral Shelf (Shallow)", "Atoll Ring", "Salt Flats", "Mesa Country",
    "Highland Lakes", "Inland Sea Rim", "Wind Carved Ridges", "Fjord Coast",
]
EXTRA_REALMS = ["Hell", "Purgatory", "Heaven's Gate"]
ALL_BIOMES = EARTH_BIOMES_44 + EXTRA_REALMS


# ----------------------------
# LOCKED WORLD RULES
# ----------------------------
EXPORT_SIZE = 2017
PREVIEW_SIZE = 1025

SEA_LEVEL = 0.5
FADE_PX = 34

USE_SHELF = True
SHELF_WIDTH_PX = 180
SHELF_DEPTH = 0.18

KALMAN_ITERS = 6

DO_EROSION = True
EROSION_ITERS = 18
EROSION_TALUS = 0.018

DO_HYDROLOGY = True
LAKE_OUTLETS = True
RIVER_MIN_ACC = 40.0
RIVER_STRENGTH = 0.55
DELTA_STRENGTH = 0.06
DELTA_RADIUS = 28

RIDGE_PRESERVE = True
RIDGE_ITERS = 2
RIDGE_PRESERVE_AMT = 0.70

DO_BEACH_CLAMP = True
BEACH_HALFWIDTH = 0.022
BEACH_FLATTEN = 0.78
UNDERWATER_SLOPE = 0.25


# ----------------------------
# Deterministic salts (integers only)
# ----------------------------
SALT = {
    "WARP_X": 43691,
    "WARP_Y": 43693,
    "DUNE": 17713,
    "GULLY": 31457,
    "GULLY2": 31459,
    "FJORD": 48121,
    "FJORD2": 48127,
    "PIT": 22091,
    "LAVA": 61695,
    "LAVA2": 61703,
    "NET": 19937,
    "NET2": 19939,
    "CRATER": 42421,
    "SINK": 20849,
    "ARCH": 55219,
    "ATOLL": 33377,
    "CALDERA": 59077,
    "LAKES": 47057,
    "BIO": 8803,
}


def stable_biome_id(name: str) -> int:
    return int(zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF)


def u32(x: int) -> int:
    return int(x & 0xFFFFFFFF)


# ----------------------------
# Biome families + profiles
# ----------------------------
def biome_family(name: str) -> str:
    if name in ["Desert Dunes", "Desert Rock Plateau", "Salt Flats"]:
        return "DESERT"
    if name in ["Canyonlands", "Badlands", "Mesa Country"]:
        return "BADLANDS"
    if name in ["Alpine Highlands", "Wind Carved Ridges", "Cratered Highlands"]:
        return "ALPINE"
    if name in ["Glacier Field", "Fjord Coast", "Tundra"]:
        return "GLACIAL"
    if name in ["Swamp", "Marshland", "Fen", "Mangrove Coast", "River Delta", "Boreal Wetlands"]:
        return "WETLANDS"
    if name in ["Volcanic Isles", "Basalt Shelf", "Lava Plains (Dormant)"]:
        return "VOLCANIC"
    if name in ["Karst Plateau", "Limestone Ridges"]:
        return "KARST"
    if name in ["Temperate Forest", "Mixed Forest", "Old Growth Forest", "Rainforest", "Redwood Valleys", "Fog Coast"]:
        return "FOREST"
    if name in ["Coastal Plains", "Oceanic Archipelago", "Coral Shelf (Shallow)", "Atoll Ring"]:
        return "COASTAL"
    if name in ["Savanna", "Steppe", "Prairie", "Mediterranean Scrub",
                "Rolling Hills", "Temperate Island", "Tropical Island", "Arid Island"]:
        return "PLAINS"
    if name in ["Highland Lakes", "Inland Sea Rim", "Taiga"]:
        return "HIGHLANDS"
    if name in ["Hell", "Purgatory", "Heaven's Gate"]:
        return "REALMS"
    return "MIXED"


def biome_profile(name: str):
    fam = biome_family(name)

    p = dict(
        base=0.44, amp=0.56,
        lac=2.0, gain=0.52,
        ridged=0.20, terraced=0.05, crater=0.00,
        warp_strength=0.010, warp_scale=2.2,
        macro=0.56,
        silhouette=0.65,
        coast_noise=0.50,
    )

    if fam == "DESERT":
        p.update(base=0.28, amp=0.70, ridged=0.10, terraced=0.10,
                 warp_strength=0.014, warp_scale=2.8, macro=0.65,
                 silhouette=0.72, coast_noise=0.55)
    elif fam == "BADLANDS":
        p.update(base=0.34, amp=0.95, ridged=0.62, terraced=0.58,
                 warp_strength=0.016, warp_scale=2.5, macro=0.68,
                 silhouette=0.68, coast_noise=0.62)
    elif fam == "ALPINE":
        p.update(base=0.56, amp=0.78, ridged=0.82, terraced=0.12,
                 warp_strength=0.012, warp_scale=1.9, macro=0.72,
                 silhouette=0.62, coast_noise=0.45)
    elif fam == "GLACIAL":
        p.update(base=0.52, amp=0.76, ridged=0.76, terraced=0.06,
                 warp_strength=0.010, warp_scale=2.0, macro=0.74,
                 silhouette=0.68, coast_noise=0.58)
    elif fam == "WETLANDS":
        p.update(base=0.40, amp=0.50, ridged=0.10, terraced=0.00,
                 warp_strength=0.012, warp_scale=3.1, macro=0.60,
                 silhouette=0.58, coast_noise=0.55)
    elif fam == "VOLCANIC":
        p.update(base=0.54, amp=0.88, ridged=0.88, terraced=0.16, crater=0.55,
                 warp_strength=0.014, warp_scale=2.2, macro=0.76,
                 silhouette=0.70, coast_noise=0.52)
    elif fam == "KARST":
        p.update(base=0.46, amp=0.72, ridged=0.40, terraced=0.10,
                 warp_strength=0.013, warp_scale=2.6, macro=0.64,
                 silhouette=0.62, coast_noise=0.55)
    elif fam == "FOREST":
        p.update(base=0.46, amp=0.62, ridged=0.22, terraced=0.02,
                 warp_strength=0.010, warp_scale=2.2, macro=0.60,
                 silhouette=0.60, coast_noise=0.50)
    elif fam == "COASTAL":
        p.update(base=0.26, amp=0.62, ridged=0.16, terraced=0.04,
                 warp_strength=0.010, warp_scale=2.9, macro=0.60,
                 silhouette=0.78, coast_noise=0.75)
    elif fam == "PLAINS":
        p.update(base=0.38, amp=0.58, ridged=0.18, terraced=0.03,
                 warp_strength=0.010, warp_scale=2.3, macro=0.56,
                 silhouette=0.58, coast_noise=0.48)
    elif fam == "HIGHLANDS":
        p.update(base=0.50, amp=0.70, ridged=0.50, terraced=0.06,
                 warp_strength=0.010, warp_scale=2.1, macro=0.70,
                 silhouette=0.60, coast_noise=0.50)
    elif fam == "REALMS":
        if name == "Hell":
            p.update(base=0.58, amp=1.00, ridged=0.94, terraced=0.68, crater=0.60,
                     warp_strength=0.020, warp_scale=2.8, macro=0.80,
                     silhouette=0.76, coast_noise=0.70)
        elif name == "Purgatory":
            p.update(base=0.46, amp=0.90, ridged=0.66, terraced=0.44, crater=0.24,
                     warp_strength=0.016, warp_scale=2.4, macro=0.74,
                     silhouette=0.70, coast_noise=0.62)
        else:
            p.update(base=0.62, amp=0.66, ridged=0.32, terraced=0.18, crater=0.00,
                     warp_strength=0.010, warp_scale=1.8, macro=0.64,
                     silhouette=0.62, coast_noise=0.55)

    accents = {
        "Atoll Ring": dict(base=0.22, amp=0.55, silhouette=0.92, coast_noise=0.88),
        "Coral Shelf (Shallow)": dict(base=0.20, amp=0.52, silhouette=0.88, coast_noise=0.82),
        "Oceanic Archipelago": dict(base=0.18, amp=0.70, silhouette=0.94, coast_noise=0.86),
        "Fjord Coast": dict(ridged=0.82, macro=0.78, silhouette=0.86),
        "Coastal Plains": dict(base=0.22, amp=0.50, ridged=0.08, silhouette=0.70),
        "River Delta": dict(base=0.32, amp=0.44, macro=0.58, silhouette=0.66),
        "Mangrove Coast": dict(base=0.28, amp=0.46, macro=0.56, silhouette=0.78),
        "Mesa Country": dict(terraced=0.74, ridged=0.56),
        "Salt Flats": dict(base=0.18, amp=0.40, ridged=0.06, silhouette=0.52),
        "Highland Lakes": dict(base=0.52, amp=0.62, macro=0.72),
        "Inland Sea Rim": dict(base=0.46, amp=0.66, macro=0.72, silhouette=0.62),
        "Rainforest": dict(base=0.42, amp=0.58, warp_strength=0.013),
        "Fog Coast": dict(base=0.34, amp=0.58, warp_strength=0.014, silhouette=0.82),
        "Volcanic Isles": dict(crater=0.62, ridged=0.92, silhouette=0.78),
        "Basalt Shelf": dict(crater=0.28, terraced=0.24),
        "Lava Plains (Dormant)": dict(crater=0.16, terraced=0.20),
    }
    if name in accents:
        p.update(accents[name])
    return p


# ----------------------------
# Math utils
# ----------------------------
def fibonacci(n: int):
    a, b = 1, 1
    out = [a, b]
    for _ in range(max(0, n - 2)):
        a, b = b, a + b
        out.append(b)
    return out[:n]


def gaussian_kernel_1d(radius: int, sigma: float):
    if radius <= 0:
        return np.array([1.0], dtype=np.float32)
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    k /= np.sum(k)
    return k.astype(np.float32)


def blur_separable(img: np.ndarray, radius: int = 2, sigma: float = 1.25):
    k = gaussian_kernel_1d(radius, sigma)
    pad = radius

    a = np.pad(img, ((0, 0), (pad, pad)), mode="reflect")
    tmp = np.zeros_like(img, dtype=np.float32)
    for i in range(img.shape[1]):
        tmp[:, i] = np.sum(a[:, i:i + 2 * pad + 1] * k[None, :], axis=1)

    b = np.pad(tmp, ((pad, pad), (0, 0)), mode="reflect")
    out = np.zeros_like(img, dtype=np.float32)
    for j in range(img.shape[0]):
        out[j, :] = np.sum(b[j:j + 2 * pad + 1, :] * k[:, None], axis=0)

    return out


# ----------------------------
# Noise core (deterministic)
# ----------------------------
def value_noise_2d(seed: int, size: int, grid: int):
    rng = np.random.default_rng(u32(seed))
    g = grid + 1
    lattice = rng.random((g, g), dtype=np.float32)

    xs = np.linspace(0, grid, size, dtype=np.float32)
    ys = np.linspace(0, grid, size, dtype=np.float32)
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, grid)
    y1 = np.clip(y0 + 1, 0, grid)
    tx = xs - x0
    ty = ys - y0

    def fade(t):
        return t * t * (3.0 - 2.0 * t)

    txf = fade(tx)
    tyf = fade(ty)

    out = np.zeros((size, size), dtype=np.float32)
    for j in range(size):
        a = lattice[y0[j], x0]
        b = lattice[y0[j], x1]
        c = lattice[y1[j], x0]
        d = lattice[y1[j], x1]
        ab = a + (b - a) * txf
        cd = c + (d - c) * txf
        out[j, :] = ab + (cd - ab) * tyf[j]

    return out


def fbm_fibonacci(seed: int, size: int, octaves: int, lacunarity: float, gain: float):
    fib = fibonacci(max(2, octaves + 2))
    ratios = [fib[i + 1] / fib[i] for i in range(octaves)]
    amps = np.array([1.0 / fib[i + 2] for i in range(octaves)], dtype=np.float32)
    amps /= np.sum(amps)

    acc = np.zeros((size, size), dtype=np.float32)
    freq = 2.0
    amp_scale = 1.0

    for i in range(octaves):
        grid = int(max(2, round(freq)))
        layer = value_noise_2d(u32(seed + 1013 * i), size, grid)
        acc += layer * amps[i] * amp_scale
        freq *= (ratios[i] * lacunarity)
        amp_scale *= gain

    acc -= acc.min()
    den = acc.max() - acc.min()
    if den > 1e-8:
        acc /= den
    return acc.astype(np.float32)


# ----------------------------
# Sampling + warp
# ----------------------------
def bilinear_sample(img: np.ndarray, x: np.ndarray, y: np.ndarray):
    H, W = img.shape
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, W - 1)
    y1 = np.clip(y0 + 1, 0, H - 1)
    x0 = np.clip(x0, 0, W - 1)
    y0 = np.clip(y0, 0, H - 1)

    tx = (x - x0).astype(np.float32)
    ty = (y - y0).astype(np.float32)

    a = img[y0, x0]
    b = img[y0, x1]
    c = img[y1, x0]
    d = img[y1, x1]

    ab = a + (b - a) * tx
    cd = c + (d - c) * tx
    return (ab + (cd - ab) * ty).astype(np.float32)


def domain_warp(seed: int, size: int, warp_scale: float, warp_strength: float):
    wx = fbm_fibonacci(u32(seed ^ SALT["WARP_X"]), size, octaves=5, lacunarity=warp_scale, gain=0.55) * 2.0 - 1.0
    wy = fbm_fibonacci(u32(seed ^ SALT["WARP_Y"]), size, octaves=5, lacunarity=warp_scale, gain=0.55) * 2.0 - 1.0
    pix = warp_strength * float(size)
    return (wx * pix).astype(np.float32), (wy * pix).astype(np.float32)


def warp_image(seed: int, img: np.ndarray, warp_scale: float, warp_strength: float):
    H, W = img.shape
    dx, dy = domain_warp(seed, H, warp_scale=warp_scale, warp_strength=warp_strength)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return bilinear_sample(img, xx + dx, yy + dy)


# ----------------------------
# Neighbor helpers
# ----------------------------
def pad_edge(x: np.ndarray, p: int = 1):
    return np.pad(x, ((p, p), (p, p)), mode="edge")


def neighbors4(x: np.ndarray):
    xp = pad_edge(x, 1)
    c = xp[1:-1, 1:-1]
    n = xp[0:-2, 1:-1]
    s = xp[2:,   1:-1]
    w = xp[1:-1, 0:-2]
    e = xp[1:-1, 2:  ]
    return c, n, s, w, e


def neighbors8(x: np.ndarray):
    xp = pad_edge(x, 1)
    c  = xp[1:-1, 1:-1]
    n  = xp[0:-2, 1:-1]
    s  = xp[2:,   1:-1]
    w  = xp[1:-1, 0:-2]
    e  = xp[1:-1, 2:  ]
    nw = xp[0:-2, 0:-2]
    ne = xp[0:-2, 2:  ]
    sw = xp[2:,   0:-2]
    se = xp[2:,   2:  ]
    return c, n, s, w, e, nw, ne, sw, se


# ----------------------------
# Shaping blocks
# ----------------------------
def apply_ridged(noise: np.ndarray, ridged: float):
    if ridged <= 0.0:
        return noise
    r = 1.0 - np.abs(2.0 * noise - 1.0)
    return (1.0 - ridged) * noise + ridged * r


def apply_terrace(h: np.ndarray, terraced: float, steps: int = 12):
    if terraced <= 0.0:
        return h
    q = np.floor(h * steps) / steps
    return (1.0 - terraced) * h + terraced * q


def apply_craters(seed: int, h: np.ndarray, strength: float, count: int = 140):
    if strength <= 0.0:
        return h
    rng = np.random.default_rng(u32(seed ^ SALT["CRATER"]))
    size = h.shape[0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    out = h.copy().astype(np.float32)

    for _ in range(count):
        cx = float(rng.uniform(0, size))
        cy = float(rng.uniform(0, size))
        r = float(rng.uniform(size * 0.010, size * 0.055))
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        bowl = np.clip(1.0 - dist / r, 0.0, 1.0)
        bowl = bowl * bowl * (3.0 - 2.0 * bowl)
        crater = (bowl * 0.35) - (bowl ** 2 * 0.55)
        out += crater * strength

    return np.clip(out, 0.0, 1.0).astype(np.float32)


def shoreline_fade_mask(size: int, fade_px: int):
    fade_px = int(max(1, min(fade_px, size // 2 - 1)))
    yy, xx = np.mgrid[0:size, 0:size]
    d_edge = np.minimum.reduce([xx, yy, size - 1 - xx, size - 1 - yy]).astype(np.float32)
    t = np.clip(d_edge / fade_px, 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def approx_distance_to_edge(size: int):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    return np.minimum.reduce([xx, yy, (size - 1 - xx), (size - 1 - yy)])


def apply_continental_shelf(h: np.ndarray, fade_px: int, shelf_width_px: int, shelf_depth: float):
    size = h.shape[0]
    d = approx_distance_to_edge(size)

    coast = np.clip(d / max(1, fade_px), 0.0, 1.0)
    coast = coast * coast * (3.0 - 2.0 * coast)

    d2 = np.clip((d - fade_px) / max(1, shelf_width_px), 0.0, 1.0)
    d2 = d2 * d2 * (3.0 - 2.0 * d2)

    depth_mask = (1.0 - coast) + coast * (1.0 - d2) * 0.6
    return np.clip(h - shelf_depth * depth_mask, 0.0, 1.0).astype(np.float32)


# ----------------------------
# Silhouette sculpt
# ----------------------------
def island_silhouette(seed: int, size: int, complexity: float, strength: float):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = (size - 1) * 0.5
    cy = (size - 1) * 0.5
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (0.5 * size)

    base = np.clip(1.0 - r, 0.0, 1.0)
    base = base * base * (3.0 - 2.0 * base)

    n = fbm_fibonacci(u32(seed + 12345), size, octaves=6, lacunarity=2.4 + 1.6 * complexity, gain=0.55)
    n = warp_image(u32(seed + 23456), n, warp_scale=2.4 + 1.4 * complexity, warp_strength=0.010 + 0.006 * complexity)
    n = (n * 2.0 - 1.0)

    coast = np.clip(base + n * (0.22 + 0.22 * complexity), 0.0, 1.0)
    coast = coast * coast * (3.0 - 2.0 * coast)

    return np.clip((1.0 - strength) * 1.0 + strength * coast, 0.0, 1.0).astype(np.float32)


# ----------------------------
# Signature passes
# ----------------------------
def directional_dunes(seed: int, size: int, direction_deg: float, freq: float, sharpness: float):
    rng = np.random.default_rng(u32(seed))
    ang = math.radians(direction_deg + float(rng.uniform(-12, 12)))
    ux, uy = math.cos(ang), math.sin(ang)

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    s = (xx * ux + yy * uy) / float(size)

    w = fbm_fibonacci(u32(seed ^ SALT["DUNE"]), size, octaves=4, lacunarity=2.8, gain=0.55)
    s2 = s * freq + (w * 0.75)

    wave = 0.5 + 0.5 * np.sin(2.0 * math.pi * s2)
    dune = np.power(wave, sharpness).astype(np.float32)
    dune = blur_separable(dune, radius=1, sigma=0.9)
    dune -= dune.min()
    dune /= (dune.max() - dune.min() + 1e-8)
    return dune.astype(np.float32)


def glacial_u_valleys(h: np.ndarray, strength: float = 0.30):
    x = h.astype(np.float32)
    sm = blur_separable(x, radius=7, sigma=3.0)
    low = np.clip((0.58 - x) / 0.58, 0.0, 1.0)
    low = low * low
    return np.clip(x * (1.0 - strength * low) + sm * (strength * low), 0.0, 1.0).astype(np.float32)


def karst_sinkholes(seed: int, h: np.ndarray, count: int = 320, strength: float = 0.18):
    rng = np.random.default_rng(u32(seed ^ SALT["SINK"]))
    size = h.shape[0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    out = h.copy().astype(np.float32)

    for _ in range(count):
        cx = float(rng.uniform(0, size))
        cy = float(rng.uniform(0, size))
        r = float(rng.uniform(size * 0.006, size * 0.020))
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        m = np.clip(1.0 - dist / r, 0.0, 1.0)
        m = m * m * (3.0 - 2.0 * m)
        out -= (m ** 2.2) * strength

    return np.clip(out, 0.0, 1.0).astype(np.float32)


def lava_flows(seed: int, h: np.ndarray, strength: float = 0.22):
    size = h.shape[0]
    flow = fbm_fibonacci(u32(seed ^ SALT["LAVA"]), size, octaves=6, lacunarity=3.0, gain=0.55)
    flow = warp_image(u32(seed ^ SALT["LAVA2"]), flow, warp_scale=3.1, warp_strength=0.010)

    ribbons = np.clip(1.0 - np.abs(flow * 2.0 - 1.0) * 2.2, 0.0, 1.0)
    ribbons = np.power(ribbons, 2.8)

    carved = np.clip(h - ribbons * strength * 0.35, 0.0, 1.0)
    levee = np.clip(ribbons - blur_separable(ribbons, radius=3, sigma=1.6), 0.0, 1.0)
    return np.clip(carved + levee * strength * 0.22, 0.0, 1.0).astype(np.float32)


def plateauize(h: np.ndarray, steps: int = 12, hardness: float = 0.72):
    q = np.floor(h * steps) / steps
    return np.clip(h * (1.0 - hardness) + q * hardness, 0.0, 1.0).astype(np.float32)


def archipelago_cones(seed: int, size: int, count: int = 18):
    rng = np.random.default_rng(u32(seed ^ SALT["ARCH"]))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    out = np.zeros((size, size), dtype=np.float32)

    for _ in range(count):
        cx = float(rng.uniform(0.20, 0.80) * (size - 1))
        cy = float(rng.uniform(0.20, 0.80) * (size - 1))
        r = float(rng.uniform(size * 0.05, size * 0.16))
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        m = np.clip(1.0 - dist / r, 0.0, 1.0)
        m = m * m * (3.0 - 2.0 * m)
        out = np.maximum(out, m * float(rng.uniform(0.55, 1.00)))

    out = blur_separable(out, radius=2, sigma=1.2)
    out -= out.min()
    out /= (out.max() - out.min() + 1e-8)
    return out.astype(np.float32)


def caldera(seed: int, size: int):
    rng = np.random.default_rng(u32(seed ^ SALT["CALDERA"]))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = (size - 1) * (0.5 + float(rng.uniform(-0.08, 0.08)))
    cy = (size - 1) * (0.5 + float(rng.uniform(-0.08, 0.08)))
    r0 = size * (0.12 + float(rng.uniform(-0.03, 0.03)))
    r1 = r0 * (1.6 + float(rng.uniform(-0.15, 0.15)))

    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    bowl = np.clip(1.0 - dist / r0, 0.0, 1.0)
    bowl = bowl * bowl * (3.0 - 2.0 * bowl)
    rim = np.clip(1.0 - np.abs(dist - r1) / (r0 * 0.35), 0.0, 1.0)
    rim = rim * rim * (3.0 - 2.0 * rim)

    return (rim * 0.25 - bowl * 0.35).astype(np.float32)


def lake_basins(seed: int, size: int, count: int = 26):
    rng = np.random.default_rng(u32(seed ^ SALT["LAKES"]))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    out = np.zeros((size, size), dtype=np.float32)

    for _ in range(count):
        cx = float(rng.uniform(0.18, 0.82) * (size - 1))
        cy = float(rng.uniform(0.18, 0.82) * (size - 1))
        r = float(rng.uniform(size * 0.02, size * 0.08))
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        m = np.clip(1.0 - dist / r, 0.0, 1.0)
        m = m * m * (3.0 - 2.0 * m)
        out = np.maximum(out, m * float(rng.uniform(0.35, 1.00)))

    out = blur_separable(out, radius=2, sigma=1.1)
    return out.astype(np.float32)


def atoll_ring_mask(seed: int, size: int):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = (size - 1) * 0.5
    cy = (size - 1) * 0.5
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (0.5 * size)

    rng = np.random.default_rng(u32(seed ^ SALT["ATOLL"]))
    r0 = 0.45 + float(rng.uniform(-0.03, 0.03))
    w  = 0.10 + float(rng.uniform(-0.02, 0.02))
    ring = np.clip(1.0 - np.abs(r - r0) / max(1e-6, w), 0.0, 1.0)
    ring = ring * ring * (3.0 - 2.0 * ring)

    lagoon = np.clip(1.0 - r / max(1e-6, r0 - w * 0.6), 0.0, 1.0)
    lagoon = lagoon * lagoon * (3.0 - 2.0 * lagoon)

    n = fbm_fibonacci(u32(seed + 9182), size, octaves=4, lacunarity=3.2, gain=0.55)
    n = warp_image(u32(seed + 9183), n, warp_scale=3.0, warp_strength=0.010)
    breaks = np.clip((n - 0.62) / 0.38, 0.0, 1.0)
    breaks = breaks * breaks
    ring = ring * (1.0 - 0.55 * breaks)

    return ring.astype(np.float32), lagoon.astype(np.float32)


# ----------------------------
# Kalman-ish smoothing
# ----------------------------
def kalman_smooth_2d(measurement: np.ndarray, iters: int = 6, blur_radius: int = 2, blur_sigma: float = 1.35):
    z = measurement.astype(np.float32)
    x = z.copy()
    P = np.full_like(z, 0.25, dtype=np.float32)
    Q = 0.02
    R = 0.08

    for _ in range(iters):
        x_pred = blur_separable(x, radius=blur_radius, sigma=blur_sigma)
        P = P + Q
        K = P / (P + R)
        x = x_pred + K * (z - x_pred)
        P = (1.0 - K) * P

    return np.clip(x, 0.0, 1.0).astype(np.float32)


# ----------------------------
# Erosion + Hydrology
# ----------------------------
def thermal_erosion(h: np.ndarray, iters: int = 18, talus: float = 0.018, amount: float = 0.55):
    x = h.astype(np.float32).copy()
    for _ in range(iters):
        c, n, s, w, e = neighbors4(x)
        dn = c - n
        ds = c - s
        dw = c - w
        de = c - e

        mn = np.maximum(dn - talus, 0.0)
        ms = np.maximum(ds - talus, 0.0)
        mw = np.maximum(dw - talus, 0.0)
        me = np.maximum(de - talus, 0.0)

        total = mn + ms + mw + me + 1e-8
        out = amount * total * 0.25

        x = x - out

        xp = pad_edge(x, 1)
        frac_n = (mn / total) * out
        frac_s = (ms / total) * out
        frac_w = (mw / total) * out
        frac_e = (me / total) * out

        xp[0:-2, 1:-1] += frac_n
        xp[2:,   1:-1] += frac_s
        xp[1:-1, 0:-2] += frac_w
        xp[1:-1, 2:  ] += frac_e

        x = np.clip(xp[1:-1, 1:-1], 0.0, 1.0)

    return x.astype(np.float32)


def fill_depressions_fast(h: np.ndarray, iters: int = 80, eps: float = 1e-4):
    x = h.astype(np.float32).copy()
    for _ in range(iters):
        c, n, s, w, e = neighbors4(x)
        mn = np.minimum(np.minimum(n, s), np.minimum(w, e))
        x = np.maximum(x, mn - eps)
    return np.clip(x, 0.0, 1.0).astype(np.float32)


def carve_lake_outlets(original: np.ndarray, filled: np.ndarray,
                       sea_level: float, lake_thresh: float = 0.002,
                       carve_depth: float = 0.02, max_len: int = 650):
    H, W = original.shape
    out = original.copy().astype(np.float32)

    lake = (filled - original) > lake_thresh
    if not np.any(lake):
        return out

    lp = pad_edge(lake.astype(np.uint8), 1).astype(bool)
    c = lp[1:-1, 1:-1]
    n = lp[0:-2, 1:-1]
    s = lp[2:,   1:-1]
    w = lp[1:-1, 0:-2]
    e = lp[1:-1, 2:  ]
    rim = c & (~(n & s & w & e))

    ys, xs = np.where(rim)
    if ys.size == 0:
        return out

    rim_heights = filled[ys, xs]
    order = np.argsort(rim_heights)[: min(14, ys.size)]
    candidates = list(zip(ys[order], xs[order]))

    for (y, x) in candidates:
        cy, cx = int(y), int(x)
        for _ in range(max_len):
            out[cy, cx] = max(0.0, out[cy, cx] - carve_depth)
            if out[cy, cx] <= sea_level + 0.001:
                break

            best_y, best_x = cy, cx
            best_h = filled[cy, cx]

            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny = cy + dy
                    nx = cx + dx
                    if 0 <= ny < H and 0 <= nx < W:
                        hh = filled[ny, nx]
                        if hh < best_h:
                            best_h = hh
                            best_y, best_x = ny, nx

            if (best_y, best_x) == (cy, cx):
                break
            cy, cx = best_y, best_x

    return np.clip(out, 0.0, 1.0).astype(np.float32)


def flow_d8(height: np.ndarray):
    h = height.astype(np.float32)
    H, W = h.shape
    yy, xx = np.mgrid[0:H, 0:W]

    c, n, s, w, e, nw, ne, sw, se = neighbors8(h)

    drops = [
        (c - n,  -1,  0),
        (c - s,   1,  0),
        (c - w,   0, -1),
        (c - e,   0,  1),
        (c - nw, -1, -1),
        (c - ne, -1,  1),
        (c - sw,  1, -1),
        (c - se,  1,  1),
    ]

    best_drop = np.zeros_like(h, dtype=np.float32)
    dst_y = yy.copy()
    dst_x = xx.copy()

    for drop, dy, dx in drops:
        better = drop > best_drop
        best_drop = np.where(better, drop, best_drop)
        cand_y = np.clip(yy + dy, 0, H - 1)
        cand_x = np.clip(xx + dx, 0, W - 1)
        dst_y = np.where(better, cand_y, dst_y)
        dst_x = np.where(better, cand_x, dst_x)

    dst = (dst_y * W + dst_x).astype(np.int32)
    order = np.argsort(h.reshape(-1))[::-1]

    acc = np.ones(H * W, dtype=np.float32)
    dst_flat = dst.reshape(-1)

    for k in order:
        j = dst_flat[k]
        if j != k:
            acc[j] += acc[k]

    return acc.reshape(H, W).astype(np.float32), dst_flat.astype(np.int32)


def river_channel_mask_from_acc(acc: np.ndarray, min_acc: float):
    a = acc / (acc.max() + 1e-8)
    thresh = min_acc / (acc.max() + 1e-8)
    ch = np.clip((a - thresh) / max(1e-6, 1.0 - thresh), 0.0, 1.0)
    return (ch ** 2.2).astype(np.float32)


def widen_channel_multiscale(channel: np.ndarray, acc: np.ndarray):
    a = acc / (acc.max() + 1e-8)
    ch1 = blur_separable(channel, radius=1, sigma=0.9)
    ch2 = blur_separable(channel, radius=3, sigma=1.6)
    ch3 = blur_separable(channel, radius=6, sigma=2.6)

    w3 = np.clip((a - 0.55) / 0.45, 0.0, 1.0)
    w2 = np.clip((a - 0.25) / 0.50, 0.0, 1.0)
    w1 = 1.0 - np.clip(w2 + 0.35 * w3, 0.0, 1.0)

    widened = w1 * ch1 + w2 * ch2 + w3 * ch3
    return np.clip(widened, 0.0, 1.0).astype(np.float32)


def carve_rivers_wide(h: np.ndarray, channel_wide: np.ndarray, strength: float = 0.55):
    inc = strength * 0.065 * (channel_wide ** 1.15)
    out = np.clip(h - inc, 0.0, 1.0).astype(np.float32)
    return blur_separable(out, radius=1, sigma=0.9)


def deposit_delta_fans(h: np.ndarray, channel_wide: np.ndarray, dst_flat: np.ndarray,
                       sea_level: float, band: float = 0.03,
                       deposit_strength: float = 0.06,
                       fan_radius: int = 28):
    H, W = h.shape
    out = h.copy().astype(np.float32)

    near_sea = np.abs(out - sea_level) <= band
    strong_river = channel_wide > 0.35

    flat = out.reshape(-1)
    ds = flat[dst_flat].reshape(H, W)
    into_sea = ds < (sea_level - 0.002)

    deltas = np.where(near_sea & strong_river & into_sea)
    if deltas[0].size == 0:
        return out

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    for y, x in zip(deltas[0][::4], deltas[1][::4]):
        k = int(y * W + x)
        j = int(dst_flat[k])
        y2, x2 = divmod(j, W)

        dy = float(y2 - y)
        dx = float(x2 - x)
        norm = math.hypot(dx, dy) + 1e-8
        ux, uy = dx / norm, dy / norm

        rx0 = int(max(0, x - fan_radius))
        rx1 = int(min(W, x + fan_radius + 1))
        ry0 = int(max(0, y - fan_radius))
        ry1 = int(min(H, y + fan_radius + 1))

        X = xx[ry0:ry1, rx0:rx1] - x
        Y = yy[ry0:ry1, rx0:rx1] - y

        along = X * ux + Y * uy
        cross = -X * uy + Y * ux

        forward = (along >= 0).astype(np.float32)
        sig_along = fan_radius * 0.55
        sig_cross = fan_radius * 0.22
        g = np.exp(-(along**2) / (2 * sig_along**2) - (cross**2) / (2 * sig_cross**2)).astype(np.float32)
        g *= forward

        local_strength = float(channel_wide[y, x])
        dep = deposit_strength * local_strength * g
        out[ry0:ry1, rx0:rx1] = np.clip(out[ry0:ry1, rx0:rx1] + dep, 0.0, 1.0)

    return out.astype(np.float32)


def ridge_preserve_smooth(h: np.ndarray, iters: int = 2, radius: int = 2, sigma: float = 1.1, preserve: float = 0.70):
    x = h.astype(np.float32)
    for _ in range(iters):
        sm = blur_separable(x, radius=radius, sigma=sigma)
        xp = pad_edge(x, 1)
        gx = np.abs(xp[1:-1, 2:] - xp[1:-1, 0:-2])
        gy = np.abs(xp[2:, 1:-1] - xp[0:-2, 1:-1])
        g = np.clip((gx + gy) * 0.5, 0.0, 1.0)
        mask = 1.0 - (g ** 0.75)
        mask = (1.0 - preserve) + preserve * mask
        x = x * (1.0 - mask) + sm * mask
    return np.clip(x, 0.0, 1.0).astype(np.float32)


def waterline_shelf_clamp(h: np.ndarray, sea_level: float, beach_halfwidth: float,
                          beach_flatten: float, underwater_slope: float):
    x = h.astype(np.float32)
    d = x - sea_level
    m = 1.0 - np.clip(np.abs(d) / max(beach_halfwidth, 1e-8), 0.0, 1.0)
    m = m * m * (3.0 - 2.0 * m)

    x_beach = x * (1.0 - beach_flatten * m) + sea_level * (beach_flatten * m)

    under = np.clip((sea_level - x_beach) / max(beach_halfwidth, 1e-8), 0.0, 1.0)
    under = under * under * (3.0 - 2.0 * under)
    x_under = x_beach + (sea_level - x_beach) * under * underwater_slope
    return np.clip(x_under, 0.0, 1.0).astype(np.float32)


def rescale_preserve_sea(h: np.ndarray, sea_level: float):
    x = h.astype(np.float32)
    below = x[x < sea_level]
    above = x[x > sea_level]

    if below.size > 0:
        mn = below.min()
        if sea_level - mn > 1e-8:
            x[x < sea_level] = sea_level - (sea_level - x[x < sea_level]) * ((sea_level - 0.0) / (sea_level - mn))

    if above.size > 0:
        mx = above.max()
        if mx - sea_level > 1e-8:
            x[x > sea_level] = sea_level + (x[x > sea_level] - sea_level) * ((1.0 - sea_level) / (mx - sea_level))

    return np.clip(x, 0.0, 1.0)


# ----------------------------
# Master generator (DETERMINISTIC)
# ----------------------------
def make_heightmap(seed: int, biome: str, size: int):
    p = biome_profile(biome)
    bid = stable_biome_id(biome)

    s0 = u32(seed)
    s1 = u32(seed * 1315423911) ^ u32(bid * 2654435761) ^ u32(SALT["BIO"] * 97531)
    s2 = u32(seed + bid * 97) ^ 0x9E3779B9

    macro = fbm_fibonacci(u32(s1), size, octaves=7, lacunarity=p["lac"], gain=p["gain"])
    micro = fbm_fibonacci(u32(s2), size, octaves=6, lacunarity=p["lac"] * 2.6, gain=max(0.45, p["gain"]))

    macro = warp_image(u32(s1 + 1111), macro, warp_scale=p["warp_scale"], warp_strength=p["warp_strength"])
    micro = warp_image(u32(s2 + 2222), micro, warp_scale=p["warp_scale"] * 1.15, warp_strength=p["warp_strength"] * 0.90)

    h = p["macro"] * macro + (1.0 - p["macro"]) * micro

    sil = island_silhouette(u32(s0 + bid), size, complexity=p["coast_noise"], strength=p["silhouette"])
    h = np.clip(h * sil, 0.0, 1.0)

    h = apply_ridged(h, p["ridged"])
    h = apply_terrace(h, p["terraced"], steps=14)
    h = apply_craters(u32(s0), h, p.get("crater", 0.0), count=160 if p.get("crater", 0.0) > 0 else 0)

    fam = biome_family(biome)

    if biome == "Atoll Ring":
        ring, lagoon = atoll_ring_mask(u32(s0 + bid), size)
        h = np.clip(h * 0.30 + ring * 0.75, 0.0, 1.0)
        h = np.clip(h - lagoon * 0.40, 0.0, 1.0)
    elif biome == "Oceanic Archipelago":
        cones = archipelago_cones(u32(s0 + bid), size, count=22)
        h = np.clip(h * 0.35 + cones * 0.75, 0.0, 1.0)
    elif fam == "DESERT":
        dunes = directional_dunes(u32(s0 + bid), size, direction_deg=35.0, freq=7.5, sharpness=4.2)
        h = np.clip(h * 0.78 + dunes * 0.35, 0.0, 1.0)
    elif fam == "BADLANDS":
        h = plateauize(h, steps=12, hardness=0.74)
        g = fbm_fibonacci(u32(s0 ^ SALT["GULLY"]), size, octaves=6, lacunarity=3.0, gain=0.55)
        g = warp_image(u32(s0 ^ SALT["GULLY2"]), g, warp_scale=3.0, warp_strength=0.012)
        gullies = np.power(np.clip(1.0 - np.abs(g * 2.0 - 1.0) * 2.0, 0.0, 1.0), 2.7)
        h = np.clip(h - gullies * 0.20, 0.0, 1.0)
    elif fam == "GLACIAL":
        h = glacial_u_valleys(h, strength=0.32)
        fj = fbm_fibonacci(u32(s0 ^ SALT["FJORD"]), size, octaves=5, lacunarity=2.6, gain=0.55)
        fj = warp_image(u32(s0 ^ SALT["FJORD2"]), fj, warp_scale=2.6, warp_strength=0.010)
        cuts = np.power(np.clip(1.0 - np.abs(fj * 2.0 - 1.0) * 2.4, 0.0, 1.0), 3.0)
        h = np.clip(h - cuts * 0.18, 0.0, 1.0)
    elif fam == "KARST":
        h = karst_sinkholes(u32(s0 + bid), h, count=360, strength=0.18)
        pit = fbm_fibonacci(u32(s0 ^ SALT["PIT"]), size, octaves=6, lacunarity=4.2, gain=0.52)
        pit = np.power(pit, 2.6)
        h = np.clip(h - pit * 0.07, 0.0, 1.0)
    elif fam == "VOLCANIC":
        h = lava_flows(u32(s0 + bid), h, strength=0.22)
        h = np.clip(h + caldera(u32(s0 + bid), size), 0.0, 1.0)
        spiky = apply_ridged(h, 0.58)
        h = np.clip(h * 0.66 + spiky * 0.34, 0.0, 1.0)
    elif fam == "WETLANDS":
        sm = blur_separable(h, radius=7, sigma=3.0)
        low = np.clip((0.60 - h) / 0.60, 0.0, 1.0)
        h = np.clip(h * (1.0 - 0.42 * low) + sm * (0.42 * low), 0.0, 1.0)
    elif fam == "FOREST":
        net = fbm_fibonacci(u32(s0 ^ SALT["NET"]), size, octaves=6, lacunarity=2.8, gain=0.55)
        net = warp_image(u32(s0 ^ SALT["NET2"]), net, warp_scale=2.6, warp_strength=0.010)
        paths = np.power(np.clip(1.0 - np.abs(net * 2.0 - 1.0) * 2.2, 0.0, 1.0), 3.4)
        h = np.clip(h - paths * 0.09, 0.0, 1.0)
    elif fam == "HIGHLANDS":
        if biome == "Highland Lakes":
            lakes = lake_basins(u32(s0 + bid), size, count=30)
            h = np.clip(h - lakes * 0.22, 0.0, 1.0)
        elif biome == "Inland Sea Rim":
            lakes = lake_basins(u32(s0 + bid), size, count=16)
            h = np.clip(h - lakes * 0.30, 0.0, 1.0)
            rim = blur_separable(lakes, radius=6, sigma=2.6) - blur_separable(lakes, radius=2, sigma=1.1)
            h = np.clip(h + np.clip(rim, 0.0, 1.0) * 0.18, 0.0, 1.0)
    elif fam == "REALMS":
        if biome == "Hell":
            h = plateauize(h, steps=14, hardness=0.80)
            spikes = apply_ridged(h, 0.88)
            h = np.clip(h * 0.52 + spikes * 0.48, 0.0, 1.0)
        elif biome == "Heaven's Gate":
            h = plateauize(h, steps=10, hardness=0.58)
            h = blur_separable(h, radius=2, sigma=1.1)

    h = kalman_smooth_2d(h, iters=KALMAN_ITERS, blur_radius=2, blur_sigma=1.35)

    if DO_EROSION:
        h = thermal_erosion(h, iters=EROSION_ITERS, talus=EROSION_TALUS, amount=0.55)

    if DO_HYDROLOGY:
        filled = fill_depressions_fast(h, iters=80, eps=1e-4)
        if LAKE_OUTLETS:
            h = carve_lake_outlets(h, filled, sea_level=SEA_LEVEL, lake_thresh=0.002, carve_depth=0.02, max_len=650)

        acc, dst_flat = flow_d8(h)
        channel = river_channel_mask_from_acc(acc, min_acc=RIVER_MIN_ACC)
        channel_wide = widen_channel_multiscale(channel, acc)
        h = carve_rivers_wide(h, channel_wide, strength=RIVER_STRENGTH)

        if DELTA_STRENGTH > 0.0 and DELTA_RADIUS > 0:
            h = deposit_delta_fans(h, channel_wide, dst_flat, sea_level=SEA_LEVEL,
                                   band=0.03, deposit_strength=DELTA_STRENGTH, fan_radius=DELTA_RADIUS)

    if RIDGE_PRESERVE:
        h = ridge_preserve_smooth(h, iters=RIDGE_ITERS, radius=2, sigma=1.1, preserve=RIDGE_PRESERVE_AMT)

    h = np.clip(h * p["amp"] + p["base"], 0.0, 1.0)

    if USE_SHELF:
        h = apply_continental_shelf(h, fade_px=FADE_PX, shelf_width_px=SHELF_WIDTH_PX, shelf_depth=SHELF_DEPTH)

    h *= shoreline_fade_mask(size, FADE_PX)

    if DO_BEACH_CLAMP:
        h = waterline_shelf_clamp(h, sea_level=SEA_LEVEL, beach_halfwidth=BEACH_HALFWIDTH,
                                  beach_flatten=BEACH_FLATTEN, underwater_slope=UNDERWATER_SLOPE)
        h = rescale_preserve_sea(h, sea_level=SEA_LEVEL)

    h[0, :] = 0.0
    h[-1, :] = 0.0
    h[:, 0] = 0.0
    h[:, -1] = 0.0

    return h.astype(np.float32)


# ----------------------------
# Export helpers
# ----------------------------
def to_png_16bit(height01: np.ndarray, path: str):
    h16 = np.clip(height01 * 65535.0 + 0.5, 0, 65535).astype(np.uint16)
    Image.fromarray(h16, mode="I;16").save(path)


# ----------------------------
# Preview label overlay
# ----------------------------
def _load_font(size: int):
    candidates = [
        "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
        "arial.ttf", "Arial.ttf",
        "segoeui.ttf", "SegoeUI.ttf",
    ]
    for f in candidates:
        try:
            return ImageFont.truetype(f, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_label_on_thumbnail(img_l: Image.Image, text: str) -> Image.Image:
    img = img_l.convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    font = _load_font(size=max(10, int(H * 0.26)))
    pad = max(4, int(W * 0.06))

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    bar_h = th + pad * 2
    y0 = H - bar_h

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)

    o.rectangle([0, y0, W, H], fill=(0, 0, 0, 190))
    o.rectangle([0, y0, W, y0 + 1], fill=(255, 255, 255, 40))

    if tw > (W - 2 * pad):
        scale = (W - 2 * pad) / max(1, tw)
        font = _load_font(size=max(8, int(font.size * scale)))
        bbox = o.textbbox((0, 0), text, font=font)
        th = bbox[3] - bbox[1]

    tx = pad
    ty = y0 + (bar_h - th) // 2 - 1
    o.text((tx + 1, ty + 1), text, font=font, fill=(0, 0, 0, 200))
    o.text((tx, ty), text, font=font, fill=(235, 235, 235, 255))

    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


# ----------------------------
# Scrollable container
# ----------------------------
class ScrollableFrame(ttk.Frame):
    def __init__(self, master, bg="#000000"):
        super().__init__(master)
        self.bg = bg

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)        # Windows
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)    # Linux up
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)    # Linux down

    def _on_inner_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.inner_id, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")


# ----------------------------
# Instructions window (2 pages with Home)
# ----------------------------
class InstructionsWindow(tk.Toplevel):
    BG = "#000000"
    FG = "#D0D0D0"
    SUB = "#9A9A9A"
    CARD = "#121212"
    BORDER = "#2C2C2C"

    def __init__(self, master, get_seed_fn, get_outdir_fn):
        super().__init__(master)
        self.title("Instructions • Metasoft Studios Heightmaps")
        self.geometry("920x820")
        self.minsize(760, 640)
        self.configure(bg=self.BG)
        self.resizable(True, True)

        self.get_seed_fn = get_seed_fn
        self.get_outdir_fn = get_outdir_fn

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.FG)
        style.configure("TButton", background="#222222", foreground=self.FG)
        style.map("TButton", background=[("active", "#3A3A3A")])

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="📘 Quick Help", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(top, text="Apple-simple steps • locked scale • consistent world", foreground=self.SUB).pack(side="left", padx=12)

        self.body = ScrollableFrame(self, bg=self.BG)
        self.body.pack(fill="both", expand=True, padx=12, pady=10)

        self.page_home = tk.Frame(self.body.inner, bg=self.BG)
        self.page_unreal = tk.Frame(self.body.inner, bg=self.BG)

        for f in (self.page_home, self.page_unreal):
            f.grid(row=0, column=0, sticky="nsew")

        self._build_home_page(self.page_home)
        self._build_unreal_page(self.page_unreal)

        self.show_home()

    def _card(self, parent):
        c = tk.Frame(parent, bg=self.CARD, highlightbackground=self.BORDER, highlightthickness=1)
        c.pack(fill="x", pady=10)
        return c

    def _h(self, parent, text):
        tk.Label(parent, text=text, bg=self.CARD, fg=self.FG, font=("Segoe UI", 13, "bold"),
                 justify="left", anchor="w").pack(fill="x", padx=14, pady=(12, 6))

    def _p(self, parent, text):
        tk.Label(parent, text=text, bg=self.CARD, fg=self.FG, font=("Segoe UI", 11),
                 justify="left", anchor="w", wraplength=840).pack(fill="x", padx=14, pady=(0, 12))

    def _build_home_page(self, root):
        # Page title
        title = tk.Label(root, text="🏠 Home — Use the Tool", bg=self.BG, fg=self.FG, font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w", pady=(0, 8))

        c1 = self._card(root)
        self._h(c1, "1) Pick your island fingerprint 🧬")
        self._p(c1,
                "✅ Enter a Bitmap Seed (1 to 2,000,000)\n"
                "• That number is the island’s ID.\n"
                "• Same seed = same terrain forever.\n"
                "• Different seed = different island.\n\n"
                "Tip: Write the seed on a sticky note like a serial number.")

        c2 = self._card(root)
        self._h(c2, "2) Choose where files go 📁")
        self._p(c2,
                "✅ Output folder should be named: heightmaps_out\n"
                "• Click “Browse…” if you want to change it.\n"
                "• The tool also saves preview thumbnails to a sister folder:\n"
                "   thumbnails_out (same parent folder).\n\n"
                "Example:\n"
                "C:\\Islands\\heightmaps_out\n"
                "C:\\Islands\\thumbnails_out")

        c3 = self._card(root)
        self._h(c3, "3) Make thumbnails first 🖼️ (recommended)")
        self._p(c3,
                "✅ Click: “Build Preview Cache + Save Thumbnails (All 47)”\n"
                "• You’ll get labeled previews you can page through.\n"
                "• It also writes 47 small PNG thumbnails to thumbnails_out.\n\n"
                "This step is fast and helps you pick the vibe you want.")

        c4 = self._card(root)
        self._h(c4, "4) Export the REAL heightmaps 🚀")
        self._p(c4,
                "✅ Click: “EXPORT ALL 47 (locked)”\n"
                "• It writes 47 files at 2017×2017, 16-bit PNG.\n"
                "• These are ready for Unreal Engine Landscape import.\n\n"
                "You will see filenames like:\n"
                "height_Temperate_Island_seed123456_2017_I16.png")

        c5 = self._card(root)
        self._h(c5, "What’s special about this generator? ✨")
        self._p(c5,
                "🌊 Mid-gray sea level (32768) means the shoreline is predictable.\n"
                "🏝️ Coast fade-to-black on ALL 4 sides makes a clean island edge.\n"
                "🗺️ Rivers + lakes + deltas make terrain read ‘real’ in-game.\n"
                "🔒 Locked scale: every island matches size so they can stitch together later.")

        nav = tk.Frame(root, bg=self.BG)
        nav.pack(fill="x", pady=10)
        ttk.Button(nav, text="➡️ Next: Import into Unreal Engine (Landscape)", command=self.show_unreal).pack(side="left")
        ttk.Button(nav, text="Copy key settings to clipboard 📋", command=self.copy_settings).pack(side="left", padx=10)

    def _build_unreal_page(self, root):
        title = tk.Label(root, text="🗺️ Unreal Engine — Import Heightmap (Landscape)", bg=self.BG, fg=self.FG,
                         font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w", pady=(0, 8))

        c0 = self._card(root)
        self._h(c0, "Golden Rule 🏆 (do NOT change these)")
        self._p(c0,
                "To keep 1,000,000 islands the same scale, your import settings must be identical every time.\n\n"
                "✅ Heightmap: 2017×2017 (this tool exports that)\n"
                "✅ Landscape Components: 32 × 32\n"
                "✅ Sections per Component: 1\n"
                "✅ Section Size (Quads): 63\n"
                "✅ Scale X/Y: 100 (1 meter per quad)\n"
                "✅ Mid-gray sea level: value 32768 maps to Z=0 in Unreal (perfect for water).")

        c1 = self._card(root)
        self._h(c1, "Step-by-step import (like an Apple setup) 🍎")
        self._p(c1,
                "1️⃣ Open Unreal Engine\n"
                "2️⃣ Create / open your level 🧱\n"
                "3️⃣ Click the Landscape tool 🗻\n"
                "   • Top toolbar: Select Mode → Landscape\n"
                "4️⃣ In Landscape, choose: “Import from File” 📄\n"
                "5️⃣ Select your heightmap PNG (I;16) ✅\n"
                "   Example file:\n"
                "   height_Temperate_Island_seed123456_2017_I16.png\n\n"
                "6️⃣ Set these EXACT values (locked):\n"
                "   ✅ Section Size: 63 Quads\n"
                "   ✅ Sections per Component: 1\n"
                "   ✅ Number of Components: 32 × 32\n\n"
                "7️⃣ Set the Scale (locked):\n"
                "   ✅ X = 100\n"
                "   ✅ Y = 100\n"
                "   ✅ Z = 100  (keep consistent; adjust gameplay with meshes/water, not scale)\n\n"
                "8️⃣ Click “Import” 🚀\n"
                "9️⃣ Add water at Z = 0 🌊\n"
                "   • Because this tool uses mid-gray sea level, Z=0 is your shoreline reference.\n\n"
                "🔟 Save the level 💾")

        c2 = self._card(root)
        self._h(c2, "If something looks wrong 😅 (2 quick checks)")
        self._p(c2,
                "✅ Check #1: Resolution\n"
                "• Must be 2017×2017.\n"
                "• If you imported 2016 or 2048, Unreal will not match the locked layout.\n\n"
                "✅ Check #2: Component settings\n"
                "• Must be 32×32 components.\n"
                "• Must be 63 quads, 1 section.\n\n"
                "If those match, your island will always be the same size.")

        c3 = self._card(root)
        self._h(c3, "Why mid-gray sea level matters 🌊")
        self._p(c3,
                "Unreal treats 16-bit heights as centered around a mid value.\n"
                "🟦 Mid-gray (32768) becomes roughly Z=0.\n"
                "So you get:\n"
                "• consistent beaches\n"
                "• consistent ocean plane\n"
                "• consistent island stitching later")

        nav = tk.Frame(root, bg=self.BG)
        nav.pack(fill="x", pady=10)
        ttk.Button(nav, text="⬅️ Home", command=self.show_home).pack(side="left")
        ttk.Button(nav, text="Copy import settings to clipboard 📋", command=self.copy_settings).pack(side="left", padx=10)

    def show_home(self):
        self.page_home.tkraise()
        self.body.canvas.yview_moveto(0.0)

    def show_unreal(self):
        self.page_unreal.tkraise()
        self.body.canvas.yview_moveto(0.0)

    def copy_settings(self):
        try:
            seed = self.get_seed_fn()
        except Exception:
            seed = "(enter seed)"
        outdir = self.get_outdir_fn()

        txt = (
            "Metasoft Locked Island Settings\n"
            "-----------------------------\n"
            f"Seed: {seed}\n"
            f"Heightmaps folder: {outdir}\n\n"
            "Heightmap:\n"
            "- 2017×2017 PNG, 16-bit grayscale (I;16)\n"
            "- Mid-gray sea level (32768)\n\n"
            "Unreal Landscape import (LOCKED):\n"
            "- Section Size (Quads): 63\n"
            "- Sections per Component: 1\n"
            "- Number of Components: 32 × 32\n"
            "- Scale X: 100\n"
            "- Scale Y: 100\n"
            "- Scale Z: 100\n\n"
            "Water:\n"
            "- Put ocean plane at Z = 0\n"
        )
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.update()
        messagebox.showinfo("Copied", "✅ Settings copied to clipboard.")


# ----------------------------
# GUI (Dark + branded + 3×3 + scroll + resizable)
# ----------------------------
class App(tk.Tk):
    SEED_MIN = 1
    SEED_MAX = 2_000_000

    GRID_COLS = 3
    GRID_ROWS = 3
    PER_PAGE = GRID_COLS * GRID_ROWS  # 9

    BG = "#000000"
    FG = "#D0D0D0"
    SUBFG = "#888888"
    CARD = "#141414"
    BTN = "#222222"
    BTN_ACTIVE = "#3A3A3A"
    BORDER = "#333333"
    ENTRY_BG = "#111111"

    def __init__(self):
        super().__init__()
        self.title("Metasoft Studios — Bitmap Heightmaps (LOCKED) v3.6")
        self.geometry("980x900")
        self.minsize(860, 740)
        self.configure(bg=self.BG)
        self.resizable(True, True)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.FG)
        style.configure("TLabelframe", background=self.BG, foreground=self.FG)
        style.configure("TLabelframe.Label", background=self.BG, foreground=self.FG)
        style.configure("TButton", background=self.BTN, foreground=self.FG, focusthickness=0, borderwidth=1)
        style.map("TButton", background=[("active", self.BTN_ACTIVE)])
        style.configure("TEntry", fieldbackground=self.ENTRY_BG, foreground=self.FG, background=self.ENTRY_BG)

        self.seed_var = tk.StringVar(value="1")
        self.outdir_var = tk.StringVar(value=os.path.abspath("./heightmaps_out"))

        self.logo_imgtk = None
        self.qr_imgtk = None
        self.footer_imgtk = None

        self.preview_thumbs = {}      # biome -> PIL.Image (RGB) labeled
        self.preview_imgtks = []      # keep refs alive
        self.preview_ready_for_seed = None
        self.page = 0

        self.sf = ScrollableFrame(self, bg=self.BG)
        self.sf.pack(fill="both", expand=True)

        self._build(self.sf.inner)
        self._load_branding_images()

    def _build(self, root):
        brand = ttk.Frame(root)
        brand.pack(fill="x", padx=12, pady=(10, 8))

        self.logo_label = ttk.Label(brand, text="(logo.png missing)")
        self.logo_label.pack(side="top", anchor="w")

        header_row = ttk.Frame(brand)
        header_row.pack(fill="x", pady=(10, 0))

        ttk.Label(
            header_row,
            text="Bitmap Heightmap Generator • LOCKED scale • 2017×2017 • 16-bit PNG • Deterministic seed fingerprint",
            foreground=self.SUBFG
        ).pack(side="left", anchor="w")

        ttk.Button(header_row, text="Instructions 📘", command=self.open_instructions).pack(side="right")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="Bitmap Seed (1..2,000,000):").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.seed_var, width=16).grid(row=0, column=1, sticky="w", padx=(8, 0))

        ttk.Label(top, text="Output folder (heightmaps_out):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.outdir_var, width=72).grid(row=1, column=1, columnspan=2, sticky="we", padx=(8, 0), pady=(8, 0))
        ttk.Button(top, text="Browse…", command=self.pick_outdir).grid(row=1, column=3, sticky="w", padx=(10, 0), pady=(8, 0))

        top.columnconfigure(2, weight=1)

        btns = ttk.Frame(root)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(btns, text="Build Preview Cache + Save Thumbnails (All 47)", command=self.build_preview_cache).pack(side="left")
        ttk.Button(btns, text="EXPORT ALL 47 (locked)", command=self.export_all).pack(side="left", padx=10)

        prev = ttk.LabelFrame(root, text="Preview (paged) — 3×3 grid (labels are baked onto thumbnails)")
        prev.pack(fill="both", expand=True, padx=12, pady=10)

        self.grid_frame = tk.Frame(prev, bg=self.BG)
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.thumb_labels = []
        for r in range(self.GRID_ROWS):
            self.grid_frame.rowconfigure(r, weight=1)
            for c in range(self.GRID_COLS):
                self.grid_frame.columnconfigure(c, weight=1)

                cell = tk.Frame(
                    self.grid_frame,
                    bg=self.CARD,
                    highlightbackground=self.BORDER,
                    highlightthickness=1
                )
                cell.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)

                img_label = tk.Label(cell, bg=self.CARD)
                img_label.pack(pady=(10, 6))

                name_label = tk.Label(
                    cell,
                    text="",
                    bg=self.CARD,
                    fg=self.SUBFG,
                    wraplength=220,
                    justify="center"
                )
                name_label.pack(pady=(0, 10))

                self.thumb_labels.append((img_label, name_label))

        pager = ttk.Frame(prev)
        pager.pack(fill="x", padx=10, pady=(0, 10))

        self.prev_btn = ttk.Button(pager, text="◀ Prev", command=self.prev_page)
        self.prev_btn.pack(side="left")

        self.page_label = ttk.Label(pager, text="Page 1 / ?")
        self.page_label.pack(side="left", padx=12)

        self.next_btn = ttk.Button(pager, text="Next ▶", command=self.next_page)
        self.next_btn.pack(side="left")

        self.status = ttk.Label(root, text="Ready.", foreground=self.SUBFG)
        self.status.pack(fill="x", padx=12, pady=(0, 10))

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", padx=12, pady=(0, 14))

        qr_row = ttk.Frame(bottom)
        qr_row.pack(fill="x")

        self.qr_label = ttk.Label(qr_row, text="(qr.png missing)")
        self.qr_label.pack(side="left")

        ttk.Label(qr_row, text="Metasoftstudios.com", font=("Segoe UI", 12, "bold"),
                  foreground="#BBBBBB").pack(side="left", padx=12)

        self.footer_label = ttk.Label(bottom, text="(footer.png missing)")
        self.footer_label.pack(anchor="w", pady=(10, 0))

    def open_instructions(self):
        InstructionsWindow(self, self._parse_seed_safe, self._ensure_outdir_safe)

    def _parse_seed_safe(self):
        try:
            return self._parse_seed()
        except Exception:
            return None

    def _ensure_outdir_safe(self):
        try:
            return self._ensure_outdir()
        except Exception:
            return os.path.abspath(self.outdir_var.get())

    def _load_branding_images(self):
        base = os.path.dirname(os.path.abspath(__file__))

        def load_exact(path, w, h):
            if not os.path.exists(path):
                return None
            img = Image.open(path).convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)

        self.logo_imgtk = load_exact(os.path.join(base, "logo.png"), 277, 75)
        if self.logo_imgtk:
            self.logo_label.configure(image=self.logo_imgtk, text="")

        self.qr_imgtk = load_exact(os.path.join(base, "qr.png"), 100, 100)
        if self.qr_imgtk:
            self.qr_label.configure(image=self.qr_imgtk, text="")

        self.footer_imgtk = load_exact(os.path.join(base, "footer.png"), 426, 100)
        if self.footer_imgtk:
            self.footer_label.configure(image=self.footer_imgtk, text="")

    def pick_outdir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get())
        if d:
            self.outdir_var.set(d)

    def _parse_seed(self) -> int:
        s = self.seed_var.get().strip()
        if not s:
            raise ValueError("Seed is empty.")
        n = int(s)
        if n < self.SEED_MIN or n > self.SEED_MAX:
            raise ValueError(f"Seed must be between {self.SEED_MIN} and {self.SEED_MAX}.")
        return n

    def _ensure_outdir(self) -> str:
        outdir = self.outdir_var.get()
        os.makedirs(outdir, exist_ok=True)
        return outdir

    def _thumbnails_outdir(self) -> str:
        outdir = os.path.abspath(self.outdir_var.get())
        parent = os.path.dirname(outdir)
        thumbs = os.path.join(parent, "thumbnails_out")
        os.makedirs(thumbs, exist_ok=True)
        return thumbs

    def total_pages(self):
        return int(math.ceil(len(ALL_BIOMES) / self.PER_PAGE))

    def render_page(self):
        total_pages = self.total_pages()
        if total_pages <= 0:
            return
        self.page = max(0, min(self.page, total_pages - 1))

        start = self.page * self.PER_PAGE
        end = min(len(ALL_BIOMES), start + self.PER_PAGE)
        page_biomes = ALL_BIOMES[start:end]

        self.preview_imgtks.clear()

        for idx in range(self.PER_PAGE):
            img_label, name_label = self.thumb_labels[idx]
            if idx < len(page_biomes) and page_biomes[idx] in self.preview_thumbs:
                biome = page_biomes[idx]
                pil_img = self.preview_thumbs[biome]
                imgtk = ImageTk.PhotoImage(pil_img)
                self.preview_imgtks.append(imgtk)
                img_label.configure(image=imgtk)
                name_label.configure(text=biome)
            else:
                img_label.configure(image="")
                name_label.configure(text="")

        self.page_label.configure(text=f"Page {self.page + 1} / {total_pages}")
        self.prev_btn.configure(state=("normal" if self.page > 0 else "disabled"))
        self.next_btn.configure(state=("normal" if self.page < total_pages - 1 else "disabled"))

    def next_page(self):
        if not self.preview_thumbs:
            self.status.config(text="Build Preview Cache first.")
            return
        self.page += 1
        self.render_page()

    def prev_page(self):
        if not self.preview_thumbs:
            self.status.config(text="Build Preview Cache first.")
            return
        self.page -= 1
        self.render_page()

    def build_preview_cache(self):
        try:
            seed = self._parse_seed()
            thumbs_dir = self._thumbnails_outdir()
        except Exception as e:
            messagebox.showerror("Input error", str(e))
            return

        if self.preview_ready_for_seed == seed and len(self.preview_thumbs) == len(ALL_BIOMES):
            self.status.config(text=f"Preview cache already built for this seed. Thumbnails are in: {thumbs_dir}")
            self.page = 0
            self.render_page()
            return

        self.status.config(text="Building preview cache for ALL 47 biomes + saving thumbnails…")
        self.update_idletasks()

        self.preview_thumbs.clear()
        self.preview_imgtks.clear()
        self.preview_ready_for_seed = seed
        self.page = 0

        thumb_px = 90  # 1/4 size thumbnails

        for i, biome in enumerate(ALL_BIOMES, start=1):
            self.status.config(text=f"Preview+Save [{i}/47] {biome}…")
            self.update_idletasks()

            h = make_heightmap(seed, biome, size=PREVIEW_SIZE)
            h8 = np.clip(h * 255.0 + 0.5, 0, 255).astype(np.uint8)
            img = Image.fromarray(h8, mode="L").resize((thumb_px, thumb_px), Image.Resampling.BILINEAR)

            img_labeled = draw_label_on_thumbnail(img, biome)
            self.preview_thumbs[biome] = img_labeled

            tag = biome.replace(" ", "_").replace("/", "_").replace("'", "")
            out_path = os.path.join(thumbs_dir, f"thumb_{tag}_seed{seed}_{thumb_px}.png")
            img_labeled.save(out_path, format="PNG", optimize=True)

        self.status.config(text=f"Preview cache built. Thumbnails saved to: {thumbs_dir}")
        self.render_page()

    def export_all(self):
        try:
            seed = self._parse_seed()
            outdir = self._ensure_outdir()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        total = len(ALL_BIOMES)
        t0 = time.time()

        for i, biome in enumerate(ALL_BIOMES, start=1):
            self.status.config(text=f"[{i}/{total}] Exporting {biome}…")
            self.update_idletasks()

            h = make_heightmap(seed, biome, size=EXPORT_SIZE)
            tag = biome.replace(" ", "_").replace("/", "_").replace("'", "")
            path = os.path.join(outdir, f"height_{tag}_seed{seed}_{EXPORT_SIZE}_I16.png")
            to_png_16bit(h, path)

        dt = time.time() - t0
        self.status.config(text=f"Done: exported {total} heightmaps in {dt:.1f}s → {outdir}")
        messagebox.showinfo("Export complete", f"Exported {total} heightmaps.\n\nFolder:\n{outdir}")


if __name__ == "__main__":
    App().mainloop()
