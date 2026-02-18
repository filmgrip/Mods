import argparse
import hashlib
import json
import logging
import math
import os
import threading
import time
import zlib
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ----------------------------
# Locked world rules
# ----------------------------
EXPORT_SIZE = 2017
PREVIEW_SIZE = 1025
SEA_LEVEL = 0.5
FADE_PX = 34

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
# Templates (user extensibility)
# ----------------------------
BIOME_TEMPLATE = {
    "Example New Biome": {
        "family": "PLAINS",          # choose one of your family keys
        "base": 0.45,
        "amp": 0.55,
        "roughness": 0.6,
        "ridge": 0.25,
        "coast": 0.7,
    }
}

LANG_TEMPLATE = {
    "en": {
        "app_title": "Fibonacci Terrain Engine",
        "seed": "Bitmap Seed (1..2,000,000):",
        "output": "Output folder (heightmaps_out):",
        "preview": "Build Preview Cache + Save Thumbnails (All 47)",
        "export": "EXPORT ALL 47 (locked)",
        "cancel": "Cancel",
        "instructions": "Instructions 📘",
        "ready": "Ready.",
    },
    "es": {
        "app_title": "Motor de Terreno Fibonacci",
        "seed": "Semilla de mapa (1..2,000,000):",
        "output": "Carpeta de salida (heightmaps_out):",
        "preview": "Construir caché de vista previa + miniaturas (47)",
        "export": "EXPORTAR LOS 47 (bloqueado)",
        "cancel": "Cancelar",
        "instructions": "Instrucciones 📘",
        "ready": "Listo.",
    },
}


def tr(lang: str, key: str) -> str:
    return LANG_TEMPLATE.get(lang, LANG_TEMPLATE["en"]).get(key, key)


# ----------------------------
# logging
# ----------------------------
logging.basicConfig(
    filename="fibonacci_terrain_engine.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def u32(x: int) -> int:
    return int(x & 0xFFFFFFFF)


def biome_family(name: str) -> str:
    if "Desert" in name or name == "Salt Flats":
        return "DESERT"
    if "Forest" in name or name in ["Rainforest", "Fog Coast", "Redwood Valleys"]:
        return "FOREST"
    if name in ["Glacier Field", "Fjord Coast", "Tundra"]:
        return "GLACIAL"
    if name in EXTRA_REALMS:
        return "REALMS"
    if "Coast" in name or "Island" in name or "Atoll" in name or "Archipelago" in name:
        return "COASTAL"
    return "PLAINS"


@dataclass(frozen=True)
class Profile:
    base: float
    amp: float
    roughness: float
    ridge: float
    coast: float


def biome_profile(name: str) -> Profile:
    fam = biome_family(name)
    if fam == "DESERT":
        return Profile(0.34, 0.66, 0.72, 0.18, 0.62)
    if fam == "FOREST":
        return Profile(0.45, 0.57, 0.52, 0.20, 0.58)
    if fam == "GLACIAL":
        return Profile(0.56, 0.62, 0.68, 0.52, 0.82)
    if fam == "REALMS":
        return Profile(0.58, 0.72, 0.78, 0.62, 0.72)
    if fam == "COASTAL":
        return Profile(0.28, 0.58, 0.56, 0.15, 0.90)
    return Profile(0.40, 0.56, 0.52, 0.25, 0.60)


def value_noise(seed: int, size: int, grid: int) -> np.ndarray:
    rng = np.random.default_rng(u32(seed))
    lattice = rng.random((grid + 1, grid + 1), dtype=np.float32)
    xs = np.linspace(0, grid, size, dtype=np.float32)
    ys = np.linspace(0, grid, size, dtype=np.float32)
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = np.minimum(x0 + 1, grid)
    y1 = np.minimum(y0 + 1, grid)
    tx = xs - x0
    ty = ys - y0
    txf = tx * tx * (3 - 2 * tx)
    tyf = ty * ty * (3 - 2 * ty)

    out = np.zeros((size, size), dtype=np.float32)
    for j in range(size):
        a = lattice[y0[j], x0]
        b = lattice[y0[j], x1]
        c = lattice[y1[j], x0]
        d = lattice[y1[j], x1]
        out[j] = (a + (b - a) * txf) * (1 - tyf[j]) + (c + (d - c) * txf) * tyf[j]
    return out


def fbm(seed: int, size: int, octaves: int = 6, lac: float = 2.0, gain: float = 0.55) -> np.ndarray:
    acc = np.zeros((size, size), dtype=np.float32)
    amp, freq = 1.0, 2.0
    norm = 0.0
    for i in range(octaves):
        acc += value_noise(seed + i * 1013, size, max(2, int(freq))) * amp
        norm += amp
        amp *= gain
        freq *= lac
    acc /= max(norm, 1e-8)
    acc -= acc.min()
    acc /= max(acc.max(), 1e-8)
    return acc


def shoreline_mask(size: int) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.minimum.reduce([xx, yy, size - 1 - xx, size - 1 - yy]).astype(np.float32)
    t = np.clip(d / FADE_PX, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def make_heightmap(seed: int, biome: str, size: int) -> np.ndarray:
    p = biome_profile(biome)
    b = u32(zlib.crc32(biome.encode("utf-8")))
    macro = fbm(u32(seed ^ b), size, octaves=6, lac=1.9 + 0.4 * p.roughness, gain=0.55)
    micro = fbm(u32(seed + b * 17), size, octaves=5, lac=2.6, gain=0.5)
    h = 0.7 * macro + 0.3 * micro
    ridged = 1.0 - np.abs(2.0 * h - 1.0)
    h = h * (1 - p.ridge) + ridged * p.ridge

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = (size - 1) * 0.5
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size * 0.5)
    coast = np.clip(1.0 - r, 0.0, 1.0)
    coast = coast * coast * (3 - 2 * coast)
    h *= (1.0 - p.coast) + p.coast * coast

    h = np.clip(h * p.amp + p.base, 0.0, 1.0)
    h *= shoreline_mask(size)
    h[0, :], h[-1, :], h[:, 0], h[:, -1] = 0, 0, 0, 0
    return h.astype(np.float32)


def to_png_16bit(height01: np.ndarray, path: str) -> None:
    h16 = np.clip(height01 * 65535.0 + 0.5, 0, 65535).astype(np.uint16)
    Image.fromarray(h16, mode="I;16").save(path)


def thumb_with_label(h: np.ndarray, biome: str) -> Image.Image:
    h8 = np.clip(h * 255 + 0.5, 0, 255).astype(np.uint8)
    img = Image.fromarray(h8, mode="L").resize((90, 90), Image.Resampling.BILINEAR).convert("RGBA")
    dr = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    dr.rectangle((0, 70, 90, 90), fill=(0, 0, 0, 180))
    dr.text((4, 75), biome[:13], fill=(230, 230, 230, 255), font=font)
    return img.convert("RGB")


def _sanitize_tag(biome: str) -> str:
    return biome.replace(" ", "_").replace("/", "_").replace("'", "")


def deterministic_self_test() -> dict:
    seed, biome = 424242, "Temperate Island"
    h1 = make_heightmap(seed, biome, PREVIEW_SIZE)
    h2 = make_heightmap(seed, biome, PREVIEW_SIZE)
    assert np.array_equal(h1, h2), "array determinism failed"

    p1 = "_det_test_1.png"
    p2 = "_det_test_2.png"
    to_png_16bit(h1, p1)
    to_png_16bit(h2, p2)
    b1 = open(p1, "rb").read()
    b2 = open(p2, "rb").read()
    os.remove(p1)
    os.remove(p2)
    assert b1 == b2, "png determinism failed"
    return {
        "array_sha256": hashlib.sha256(h1.tobytes()).hexdigest(),
        "png_sha256": hashlib.sha256(b1).hexdigest(),
        "ok": True,
    }


class App(tk.Tk):
    def __init__(self, lang: str = "en"):
        super().__init__()
        self.lang = lang
        self.title(tr(lang, "app_title"))
        self.geometry("1020x860")
        self.configure(bg="#000000")
        self.seed_var = tk.StringVar(value="1")
        self.out_var = tk.StringVar(value=os.path.abspath("./heightmaps_out"))
        self.status_var = tk.StringVar(value=tr(lang, "ready"))
        self.cancel_flag = threading.Event()
        self.preview_cache = {}
        self.page = 0
        self._refs = []

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#000000")
        style.configure("TLabel", background="#000000", foreground="#D0D0D0")
        style.configure("TButton", background="#202020", foreground="#E0E0E0")

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=12)
        ttk.Label(top, text=tr(lang, "seed")).grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.seed_var, width=18).grid(row=0, column=1, sticky="w")
        ttk.Label(top, text=tr(lang, "output")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.out_var, width=72).grid(row=1, column=1, sticky="we", pady=(8, 0))
        ttk.Button(top, text="Browse…", command=self.pick_out).grid(row=1, column=2, padx=8, pady=(8, 0))
        ttk.Button(top, text=tr(lang, "instructions"), command=self.instructions).grid(row=0, column=2, padx=8)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=8)
        ttk.Button(bar, text=tr(lang, "preview"), command=self.start_preview).pack(side="left")
        ttk.Button(bar, text=tr(lang, "export"), command=self.start_export).pack(side="left", padx=8)
        ttk.Button(bar, text=tr(lang, "cancel"), command=self.cancel_flag.set).pack(side="left")

        self.pb = ttk.Progressbar(self, mode="determinate", maximum=len(ALL_BIOMES))
        self.pb.pack(fill="x", padx=12)
        ttk.Label(self, textvariable=self.status_var).pack(fill="x", padx=12, pady=8)

        self.grid_frame = tk.Frame(self, bg="#000000")
        self.grid_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self.cells = []
        for r in range(3):
            self.grid_frame.rowconfigure(r, weight=1)
            for c in range(3):
                self.grid_frame.columnconfigure(c, weight=1)
                cell = tk.Frame(self.grid_frame, bg="#151515", highlightbackground="#333333", highlightthickness=1)
                cell.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
                im = tk.Label(cell, bg="#151515")
                im.pack(pady=8)
                nm = tk.Label(cell, bg="#151515", fg="#999999", text="")
                nm.pack(pady=(0, 8))
                self.cells.append((im, nm))

        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(nav, text="◀ Prev", command=self.prev_page).pack(side="left")
        ttk.Button(nav, text="Next ▶", command=self.next_page).pack(side="left", padx=8)

    def instructions(self):
        msg = (
            "Locked rules:\n"
            f"- EXPORT_SIZE={EXPORT_SIZE}\n- PREVIEW_SIZE={PREVIEW_SIZE}\n"
            f"- SEA_LEVEL={SEA_LEVEL}\n- FADE_PX={FADE_PX}\n"
            "- Export ALL 47 is default behavior\n\n"
            "Packaging template:\n"
            "pyinstaller --onefile --noconsole fibonacci_terrain_engine.py\n"
            "Reproducible build notes:\n"
            "1) pin Python + Pillow + numpy versions\n2) set TZ/locale\n3) build in clean venv"
        )
        messagebox.showinfo("Instructions", msg)

    def pick_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get())
        if d:
            self.out_var.set(d)

    def parse_seed(self) -> int:
        s = int(self.seed_var.get().strip())
        if s < 1 or s > 2_000_000:
            raise ValueError("Seed must be 1..2,000,000")
        return s

    def thumbs_dir(self):
        out = os.path.abspath(self.out_var.get())
        d = os.path.join(os.path.dirname(out), "thumbnails_out")
        os.makedirs(d, exist_ok=True)
        return d

    def start_preview(self):
        threading.Thread(target=self.build_preview, daemon=True).start()

    def build_preview(self):
        self.cancel_flag.clear()
        seed = self.parse_seed()
        tdir = self.thumbs_dir()
        self.preview_cache.clear()
        for i, biome in enumerate(ALL_BIOMES, start=1):
            if self.cancel_flag.is_set():
                self.status_var.set("Preview canceled.")
                return
            h = make_heightmap(seed, biome, PREVIEW_SIZE)
            img = thumb_with_label(h, biome)
            self.preview_cache[biome] = img
            img.save(os.path.join(tdir, f"thumb_{_sanitize_tag(biome)}_seed{seed}_90.png"), "PNG", optimize=True)
            self.pb["value"] = i
            self.status_var.set(f"Preview [{i}/47] {biome}")
        self.page = 0
        self.after(0, self.render_page)

    def start_export(self):
        threading.Thread(target=self.export_all, daemon=True).start()

    def export_all(self):
        self.cancel_flag.clear()
        seed = self.parse_seed()
        out = os.path.abspath(self.out_var.get())
        os.makedirs(out, exist_ok=True)
        t0 = time.time()
        for i, biome in enumerate(ALL_BIOMES, start=1):
            if self.cancel_flag.is_set():
                self.status_var.set("Export canceled.")
                return
            h = make_heightmap(seed, biome, EXPORT_SIZE)
            path = os.path.join(out, f"height_{_sanitize_tag(biome)}_seed{seed}_{EXPORT_SIZE}_I16.png")
            to_png_16bit(h, path)
            self.pb["value"] = i
            self.status_var.set(f"Export [{i}/47] {biome}")
        dt = time.time() - t0
        logging.info("Export complete seed=%s seconds=%.2f out=%s", seed, dt, out)
        self.status_var.set(f"Done: {len(ALL_BIOMES)} in {dt:.1f}s → {out}")

    def render_page(self):
        keys = ALL_BIOMES[self.page * 9:(self.page + 1) * 9]
        self._refs.clear()
        for i in range(9):
            im, nm = self.cells[i]
            if i < len(keys) and keys[i] in self.preview_cache:
                pic = ImageTk.PhotoImage(self.preview_cache[keys[i]])
                self._refs.append(pic)
                im.config(image=pic)
                nm.config(text=keys[i])
            else:
                im.config(image="")
                nm.config(text="")

    def next_page(self):
        self.page = min((len(ALL_BIOMES)-1)//9, self.page + 1)
        self.render_page()

    def prev_page(self):
        self.page = max(0, self.page - 1)
        self.render_page()


def main():
    ap = argparse.ArgumentParser(description="Fibonacci Terrain Engine")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(deterministic_self_test(), indent=2))
        return
    App(lang=args.lang).mainloop()


if __name__ == "__main__":
    main()
