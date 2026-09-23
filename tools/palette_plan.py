#!/usr/bin/env python3
"""The sixteen CGB palettes of every palette set a build ships, their owners,
and the nearest slot for a proposed indexed PNG.

    python tools/palette_plan.py                  # owners and RGB555 values, every set
    python tools/palette_plan.py --swatches out.png  # a swatch sheet (an authoring aid, never a build input)
    python tools/palette_plan.py --propose sprite.png  # nearest OBJ (or BG) palette to the PNG's colours
    python tools/palette_plan.py --set 1 --propose sprite.png  # against the reactor set

The values come from a fresh in-memory build of the current configuration,
read back from the `bg_palettes` table (128 bytes per set, BG then OBJ), so
they are the bytes the console writes, not a copy of the source.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_rom as br  # noqa: E402

BG_OWNERS = {0: "structure walls, upper half (colour 0 is the ceiling)", 1: "HUD",
             2: "structure walls, lower half (colour 0 is the floor)", 3: "door faces, upper",
             4: "door faces, lower", 5: "machinery faces, upper", 6: "machinery faces, lower", 7: "screens"}
OBJ_OWNERS = {0: "weapon", 1: "Sentinel", 2: "drops", 3: "muzzle flash and decor", 4: "decor and the reticle",
              5: "the weapon's second palette", 6: "warden", 7: "skirmisher"}


def rgb555_to_rgb(value: int) -> tuple[int, int, int]:
    return tuple((value >> shift) & 31 for shift in (0, 5, 10))


def palettes(rom: bytes, assembler, palette_set: int = 0) -> tuple[list[list[int]], list[list[int]]]:
    """The BG and OBJ palettes of one set: 128 bytes per set from
    `bg_palettes`, BG first, exactly as `init_palettes` uploads them."""
    out = []
    for half in range(2):
        base = assembler.labels["bg_palettes"] + palette_set * 128 + half * 64
        words = [rom[base + i] | (rom[base + i + 1] << 8) for i in range(0, 64, 2)]
        out.append([words[p * 4:(p + 1) * 4] for p in range(8)])
    return out[0], out[1]


def describe(kind: str, table: list[list[int]], owners: dict[int, str]) -> list[str]:
    lines = [f"{kind} palettes"]
    for index, colours in enumerate(table):
        swatch = "  ".join(f"{c:04X}=({r:2d},{g:2d},{b:2d})" for c in colours for r, g, b in (rgb555_to_rgb(c),))
        lines.append(f"  {index}: {owners[index]:44s} {swatch}")
    return lines


def png_colours(path: Path) -> list[tuple[int, int, int]]:
    from PIL import Image
    image = Image.open(path)
    if image.mode != "P":
        raise SystemExit(f"{path}: a proposed asset is an indexed PNG")
    palette = image.getpalette()[:12]
    return [tuple(round(c * 31 / 255) for c in palette[i:i + 3]) for i in range(0, 12, 3)]


def nearest(colours: list[tuple[int, int, int]], table: list[list[int]], *, skip_zero: bool) -> list[tuple[int, int]]:
    """(palette index, summed distance) sorted by distance; index 0 is
    transparent for objects and is skipped there."""
    ranked = []
    for index, slot in enumerate(table):
        slot_rgb = [rgb555_to_rgb(c) for c in slot]
        pairs = list(zip(colours, slot_rgb))[1 if skip_zero else 0:]
        ranked.append((index, sum(abs(a - b) for want, have in pairs for a, b in zip(want, have))))
    return sorted(ranked, key=lambda item: item[1])


def write_swatches(path: Path, bg: list[list[int]], obj: list[list[int]]) -> None:
    from PIL import Image
    cell = 24
    image = Image.new("RGB", (cell * 4 * 2 + cell, cell * 8))
    for column, table in enumerate((bg, obj)):
        for row, colours in enumerate(table):
            for i, value in enumerate(colours):
                r, g, b = rgb555_to_rgb(value)
                x = column * (cell * 4 + cell) + i * cell
                image.paste((r * 255 // 31, g * 255 // 31, b * 255 // 31), (x, row * cell, x + cell, (row + 1) * cell))
    image.save(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--swatches", type=Path, help="write a swatch sheet PNG (authoring aid)")
    parser.add_argument("--propose", type=Path, help="an indexed PNG whose colours to match to a palette")
    parser.add_argument("--bg", action="store_true", help="match --propose against BG palettes instead of OBJ")
    parser.add_argument("--set", type=int, default=0, help="palette set (episode) for --swatches and --propose")
    args = parser.parse_args(argv)
    rom, assembler, metadata = br.make_rom()
    names = metadata["palette_set_names"]
    if not 0 <= args.set < len(names):
        raise SystemExit(f"--set: the build has sets 0..{len(names) - 1} ({', '.join(names)})")
    print(f"configuration {metadata['configuration_id']}")
    for index, name in enumerate(names):
        bg, obj = palettes(rom, assembler, index)
        print(f"\npalette set {index} ({name})")
        print("\n".join(describe("BG", bg, BG_OWNERS)))
        print("\n".join(describe("OBJ", obj, OBJ_OWNERS)))
    bg, obj = palettes(rom, assembler, args.set)
    if args.swatches:
        write_swatches(args.swatches, bg, obj)
        print(f"swatches (set {args.set}): {args.swatches}")
    if args.propose:
        colours = png_colours(args.propose)
        table, owners = (bg, BG_OWNERS) if args.bg else (obj, OBJ_OWNERS)
        print(f"\n{args.propose}: RGB555 colours {colours} against set {args.set}")
        for index, distance in nearest(colours, table, skip_zero=not args.bg)[:3]:
            print(f"  palette {index} ({owners[index]}): distance {distance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
