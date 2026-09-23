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

from .texture_reference import (DELTA_CLASSES, PHASE_STEPS, SHADE_SETS, TEXEL_ROWS, TEXELS, TEXTURE_SETS, Texture,
                                make_row_windows, window_planes)

TEXTURE_DIR = Path(__file__).resolve().parents[2] / "assets" / "textures"
# Texture indices. `texture_reference.TEXTURE_SETS` maps each palette set's
# surface profiles (structure, machinery, door) onto these: Sable Outpost
# 0 1 2, Reactor Deep 3 4 2, Signal Spire 5 6 2. The first three keep their
# indices and banks, so the first episode's windows never move.
TEXTURE_NAMES = ("steel_panel", "machinery_grille", "door_plate",
                 "reactor_plate", "reactor_pipes", "spire_hull", "spire_array")
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
    """One (texture, shade) block: for class and phase, sixteen bytes - the
    eight rows' plane-0 bytes, then their plane-1 bytes. Split by plane, the
    kernel's row accumulator addresses a row with its high byte alone: the
    cache sits at a sixteen-aligned address and row v's planes are at +v
    and +8+v (docs/TEXTURED_WALLS.md)."""
    windows = make_row_windows(textures())
    out = bytearray()
    for k in range(len(DELTA_CLASSES)):
        for phase in range(TEXELS * PHASE_STEPS):
            planes = [window_planes(windows[texture_index, shade, k, phase, v]) for v in range(TEXEL_ROWS)]
            out += bytes(plane0 for plane0, _ in planes) + bytes(plane1 for _, plane1 in planes)
    assert len(out) == BLOCK_BYTES
    return bytes(out)


def block_index(texture_index: int, shade: int) -> int:
    return texture_index * SHADE_SETS + shade


def block_location(texture_index: int, shade: int, banks: tuple[int, ...]) -> tuple[int, int]:
    """(ROM bank, address in the switchable window) of a block: three blocks
    to a bank, banks taken in the order given."""
    block = block_index(texture_index, shade)
    if block // BLOCKS_PER_BANK >= len(banks):
        raise ValueError("the texture blocks need more window banks than the layout gives them")
    return banks[block // BLOCKS_PER_BANK], 0x4000 + (block % BLOCKS_PER_BANK) * BLOCK_BYTES


def window_payloads(banks: tuple[int, ...]) -> list[tuple[int, int, bytes]]:
    """(bank, offset within the bank, bytes) for every block."""
    out = []
    for t in range(len(textures())):
        for shade in range(SHADE_SETS):
            bank, address = block_location(t, shade, banks)
            out.append((bank, address - 0x4000, window_block(t, shade)))
    return out


def block_directory(banks: tuple[int, ...]) -> bytes:
    """The console's directory: per texture set, per surface profile, per
    shade, three bytes (bank, address low, address high). `load_level`
    points `TEX_DIRECTORY` at its level's set."""
    out = bytearray()
    for texture_set in TEXTURE_SETS:
        for texture in texture_set:
            for shade in range(SHADE_SETS):
                bank, address = block_location(texture, shade, banks)
                out += bytes((bank, address & 0xFF, address >> 8))
    return bytes(out)


def evidence() -> dict:
    return {"textures": [t.name for t in textures()], "texture_sets": [list(t) for t in TEXTURE_SETS], "block_bytes": BLOCK_BYTES,
            "blocks": len(textures()) * SHADE_SETS, "banks": (len(textures()) * SHADE_SETS + BLOCKS_PER_BANK - 1) // BLOCKS_PER_BANK}
