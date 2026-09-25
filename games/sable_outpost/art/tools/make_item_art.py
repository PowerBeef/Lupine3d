#!/usr/bin/env python3
"""The placed items' cels (native/items.png). Never called by ROM builds.

One 8x8 cel per frame, left to right, each an indexed four-colour image
(0 transparent, 1 the dark outline, 2 the body, 3 the highlight). The console
draws a cel in the OBJ palette its item type names (game.json `items`), so
one card cel is an amber card in the effects palette and a teal card in the
decor palette. The medkit and card are the drop cels (native/drops.png),
copied, so a medkit on the floor and one an enemy left look the same.

- stim: a one-dose injector, upright, green in the drops palette.
- slugs: a box of four shells seen from the front, amber brass caps.
- cells: a charge cell, a squat battery with a lit band.
- armour: a plate carrier, shoulders and a centre seam.
- case: a weapon case lying flat, with its two latches.

`--check` verifies the committed image and manifest record are exactly what
this script makes.
"""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image

ART = Path(__file__).resolve().parents[1]
SHEET = ART / "native" / "items.png"
DROPS = ART / "native" / "drops.png"
MANIFEST = ART / "sprites.json"
RECORD = "items"
# The drops palette, for viewing the file; the console uses the item's own.
VIEW_PALETTE = [0, 0, 0, 16, 40, 32, 40, 146, 90, 219, 235, 186]

CELS = {
    "stim": (
        "........",
        "...11...",
        "...33...",
        "..1221..",
        "..1231..",
        "..1221..",
        "..1111..",
        "........",
    ),
    "slugs": (
        "........",
        "........",
        ".3.3.3..",
        ".2.2.2..",
        "1111111.",
        "1222221.",
        "1111111.",
        "........",
    ),
    "cells": (
        "........",
        "...11...",
        "..1111..",
        ".122221.",
        ".133331.",
        ".122221.",
        ".111111.",
        "........",
    ),
    "armour": (
        "........",
        ".11..11.",
        ".121121.",
        ".122221.",
        ".123221.",
        ".122221.",
        "..1111..",
        "........",
    ),
    "case": (
        "........",
        "........",
        "........",
        "11111111",
        "12322321",
        "12222221",
        "11111111",
        "........",
    ),
}
# The sheet's frames, in order: the drop cels first.
FRAMES = ("medkit", "stim", "slugs", "cells", "armour", "card", "case")


def build() -> Image.Image:
    drops = Image.open(DROPS)
    sheet = Image.new("P", (8 * len(FRAMES), 8), 0)
    sheet.putpalette(VIEW_PALETTE + [0] * (768 - len(VIEW_PALETTE)))
    for index, name in enumerate(FRAMES):
        if name in ("medkit", "card"):
            cel = drops.crop((0 if name == "medkit" else 8, 0, 8 if name == "medkit" else 16, 8))
            sheet.paste(cel, (index * 8, 0))
            continue
        for y, row in enumerate(CELS[name]):
            for x, pixel in enumerate(row):
                sheet.putpixel((index * 8 + x, y), 0 if pixel == "." else int(pixel))
    return sheet


def encoded(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, format="PNG", optimize=False, transparency=0)
    return out.getvalue()


def record(data: bytes) -> dict:
    return {"file": "native/items.png", "size": [8, 8], "frames": list(FRAMES), "ticks": [1] * len(FRAMES),
            "anchor": [4, 8], "palette": [[0, 0, 0], [16, 40, 32], [40, 146, 90], [219, 235, 186]],
            "sha256": hashlib.sha256(data).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the committed sheet and its record")
    args = parser.parse_args()
    data = encoded(build())
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.check:
        if not SHEET.is_file() or SHEET.read_bytes() != data:
            sys.exit(f"{SHEET} is not what this script makes")
        if manifest["assets"].get(RECORD) != record(data):
            sys.exit(f"{MANIFEST}: the {RECORD!r} record is not what this script makes")
        print("items: up to date")
        return
    SHEET.write_bytes(data)
    manifest["assets"][RECORD] = record(data)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SHEET.relative_to(ART.parent)} and its record")


if __name__ == "__main__":
    main()
