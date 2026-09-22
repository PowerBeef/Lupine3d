"""Authored wall textures and the ROM tables the textured kernel reads.

A texture is an indexed 16x8 PNG under `assets/textures/` whose pixel values
are colour indices 1..3 (2 lit, 3 shaded, 1 deep); index 0 is the outside
and never appears in a texture. The compiler mirrors every texture about
the horizon by construction (docs/TEXTURED_WALLS.md), so nothing here is
generated: builds read the checked-in PNGs and never call image generation.

The tables are exactly the ones `texture_reference` defines: the row
windows `W[texture][shade][stride class][phase][row]` as two plane bytes,
laid out in 5 KiB blocks per (texture, shade), three blocks per ROM bank.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from .texture_reference import (DELTA_CLASSES, PHASE_STEPS, SHADE_SETS, TEXEL_ROWS, TEXELS, Texture,
                                make_row_windows)

TEXTURE_DIR = Path(__file__).resolve().parents[2] / "assets" / "textures"
# The order is the texture index a surface profile selects (structure,
# machinery, door); a level's texture set will name these in Phase 4.
TEXTURE_NAMES = ("steel_panel", "machinery_grille", "door_plate")
BLOCK_BYTES = len(DELTA_CLASSES) * TEXELS * PHASE_STEPS * TEXEL_ROWS * 2   # 5,120
BLOCKS_PER_BANK = 3


def load_texture(name: str) -> Texture:
    path = TEXTURE_DIR / f"{name}.png"
    image = Image.open(path)
    if image.mode != "P":
        raise ValueError(f"{path}: textures are indexed PNGs")
    if image.size != (TEXELS, TEXEL_ROWS):
        raise ValueError(f"{path}: a texture is {TEXELS}x{TEXEL_ROWS} texels, authored for the upper half")
    pixels = image.load()
    rows = tuple(tuple(int(pixels[u, v]) for u in range(TEXELS)) for v in range(TEXEL_ROWS))
    return Texture(name, rows)


@lru_cache(maxsize=1)
def textures() -> tuple[Texture, ...]:
    return tuple(load_texture(name) for name in TEXTURE_NAMES)


def window_block(texture_index: int, shade: int) -> bytes:
    """One (texture, shade) block: for class, phase, row -> plane0, plane1."""
    windows = make_row_windows(textures())
    out = bytearray()
    for k in range(len(DELTA_CLASSES)):
        for phase in range(TEXELS * PHASE_STEPS):
            for v in range(TEXEL_ROWS):
                texels = windows[texture_index, shade, k, phase, v]
                plane0 = plane1 = 0
                for i, colour in enumerate(texels):
                    if colour & 1: plane0 |= 0x80 >> i
                    if colour & 2: plane1 |= 0x80 >> i
                out += bytes((plane0, plane1))
    assert len(out) == BLOCK_BYTES
    return bytes(out)


def block_index(texture_index: int, shade: int) -> int:
    return texture_index * SHADE_SETS + shade


def block_location(texture_index: int, shade: int, base_bank: int) -> tuple[int, int]:
    """(ROM bank, address in the switchable window) of a block."""
    block = block_index(texture_index, shade)
    return base_bank + block // BLOCKS_PER_BANK, 0x4000 + (block % BLOCKS_PER_BANK) * BLOCK_BYTES


def window_payloads(base_bank: int) -> list[tuple[int, int, bytes]]:
    """(bank, offset within the bank, bytes) for every block."""
    out = []
    for t in range(len(textures())):
        for shade in range(SHADE_SETS):
            bank, address = block_location(t, shade, base_bank)
            out.append((bank, address - 0x4000, window_block(t, shade)))
    return out


def block_directory(base_bank: int) -> bytes:
    """Three bytes per block for the console: bank, address low, address high."""
    out = bytearray()
    for t in range(len(textures())):
        for shade in range(SHADE_SETS):
            bank, address = block_location(t, shade, base_bank)
            out += bytes((bank, address & 0xFF, address >> 8))
    return bytes(out)


def evidence() -> dict:
    return {"textures": [t.name for t in textures()], "block_bytes": BLOCK_BYTES,
            "blocks": len(textures()) * SHADE_SETS, "banks": (len(textures()) * SHADE_SETS + BLOCKS_PER_BANK - 1) // BLOCKS_PER_BANK}
