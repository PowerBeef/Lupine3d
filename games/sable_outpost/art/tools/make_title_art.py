#!/usr/bin/env python3
"""The title screen's wordmark and emblem. Never called by ROM builds.

Both are indexed four-colour images in the screen palette's order (0 the
ground, 1 grey, 2 ivory, 3 teal), committed as source assets under
../title/ and drawn by the screen composer where screens.json places them.

- The wordmark spells SABLE in slab capitals built from 4x4 blocks: ivory
  above, a dithered fade into teal below, a one-pixel grey drop shadow, and
  one dark row cut straight across the name where the helmet's visor slit
  would be.
- The emblem is the owner-approved armoured helmet, the HUD portrait's first
  frame (native/helmet_steel.png) at twice its size, pixel for pixel: it is
  derived here, never redrawn.

`--check` verifies the committed images are exactly what this script makes.
"""
import argparse
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image

ART = Path(__file__).resolve().parents[1]
TITLE = ART / "title"
WORDMARK = TITLE / "wordmark.png"
EMBLEM = TITLE / "emblem.png"
# The screen palette (BG 1, the HUD's): for viewing the files; the console
# draws the indices in whatever BG 1 holds.
VIEW_PALETTE = [16, 24, 32, 102, 119, 122, 238, 230, 197, 82, 132, 132]

BLOCK = 4
LETTERS = {
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
}
WORD = "SABLE"
LETTER_GAP = 4
SLIT_ROW = 14          # the dark cut across the name
FADE_ROW = 16          # teal dither starts here
SOLID_TEAL_ROW = 22    # and is solid from here down


def _indexed(width: int, height: int) -> Image.Image:
    image = Image.new("P", (width, height), 0)
    image.putpalette(VIEW_PALETTE + [0] * (768 - len(VIEW_PALETTE)))
    return image


def wordmark() -> Image.Image:
    letter_width, letter_height = 5 * BLOCK, 7 * BLOCK
    ink = set()
    for index, letter in enumerate(WORD):
        left = index * (letter_width + LETTER_GAP)
        for row, pattern in enumerate(LETTERS[letter]):
            for column, cell in enumerate(pattern):
                if cell == "#":
                    ink.update((left + column * BLOCK + x, row * BLOCK + y)
                               for y in range(BLOCK) for x in range(BLOCK))
    width = len(WORD) * letter_width + (len(WORD) - 1) * LETTER_GAP + 1
    image = _indexed(-(-width // 8) * 8, -(-(letter_height + 1) // 8) * 8)
    offset = (image.width - width) // 2
    for x, y in ink:                       # the shadow, one pixel down and right
        image.putpixel((offset + x + 1, y + 1), 1)
    for x, y in ink:
        if y == SLIT_ROW:
            value = 0
        elif y >= SOLID_TEAL_ROW or (y >= FADE_ROW and (x + y) % 2 == 0):
            value = 3
        else:
            value = 2
        image.putpixel((offset + x, y), value)
    return image


def emblem() -> Image.Image:
    helmet = Image.open(ART / "native" / "helmet_steel.png")
    assert helmet.mode == "P" and helmet.size[1] == 16, helmet.size
    image = _indexed(32, 32)
    for y in range(32):
        for x in range(32):
            image.putpixel((x, y), helmet.getpixel((x // 2, y // 2)))
    return image


def encoded(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the committed images")
    args = parser.parse_args()
    made = {WORDMARK: encoded(wordmark()), EMBLEM: encoded(emblem())}
    if args.check:
        stale = [path.name for path, data in made.items() if not path.is_file() or path.read_bytes() != data]
        if stale:
            sys.exit(f"title art differs from its derivation: {', '.join(stale)} (run this script)")
        print("title art matches its derivation")
        return
    TITLE.mkdir(parents=True, exist_ok=True)
    for path, data in made.items():
        path.write_bytes(data)
        print(f"wrote {path.relative_to(ART.parent)}")


if __name__ == "__main__":
    main()
