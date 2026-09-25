#!/usr/bin/env python3
"""The Sentinel's close cels: the master at 16x48. Never called by ROM builds.

The near cel is the master's figure at 16x32 (`adapt_sable_art.py`); this
sheet is the same twelve crops at half as tall again, so an enemy within
about a cell is drawn 48 pixels tall, four fifths of a wall at that range,
with its head well above the horizon. It keeps the near cel's width: the
engine draws it as two columns of three 8x16 objects (six, not the nine a
proportional 24-pixel figure would take, which would leave room for one
such enemy per scanline). The death cels keep the near sheet's proportions
(27, 20 and 10 of 32 rows become 40, 30 and 15 of 48).

The result is indexed native art, committed as a source asset and recorded
in ../sprites.json as `sentinel_close`; `--check` verifies the committed
sheet and its record are exactly what this derivation produces.
"""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image

ART = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapt_sable_art import NAMES, PALETTES, adapt, indexed  # noqa: E402

MASTER = ART / "masters" / "sentinel.png"
TARGET = ART / "native" / "sentinel_close.png"
SIZE = (16, 48)
HEIGHTS = [48] * 9 + [40, 30, 15]
TICKS = [32, 32, 8, 8, 8, 8, 4, 4, 8, 12, 12, 12]


def derive() -> Image.Image:
    source = Image.open(MASTER)
    sheet = indexed((SIZE[0] * 12, SIZE[1]), PALETTES["sentinel"])
    for i in range(12):
        # The near sheet's crops of the master (adapt_sable_art.main).
        x, y = i % 4, i // 4
        box = (x * 256, [130, 550, 1010][y], (x + 1) * 256, [485, 915, 1360][y])
        sheet.paste(adapt(source, box, SIZE, PALETTES["sentinel"], HEIGHTS[i]), (i * SIZE[0], 0))
    return sheet


def encoded(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", transparency=0, optimize=False)
    return buffer.getvalue()


def record(data: bytes) -> dict:
    return {"file": "native/sentinel_close.png", "size": list(SIZE), "frames": NAMES, "ticks": TICKS,
            "anchor": [SIZE[0] // 2, SIZE[1]], "palette": [list(c) for c in PALETTES["sentinel"]],
            "sha256": hashlib.sha256(data).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the committed sheet and its manifest record")
    args = parser.parse_args()
    data = encoded(derive())
    manifest_path = ART / "sprites.json"
    manifest = json.loads(manifest_path.read_text())
    if args.check:
        if TARGET.read_bytes() != data:
            sys.exit(f"{TARGET.name} differs from its derivation; rerun without --check")
        if manifest["assets"].get("sentinel_close") != record(data):
            sys.exit("sprites.json's sentinel_close record differs from the derivation")
        print(f"{TARGET.name} matches its derivation")
        return
    TARGET.write_bytes(data)
    assets = manifest["assets"]
    # Keep the manifest's order: the close sheet sits before the near one.
    manifest["assets"] = {**({"sentinel_close": record(data)}), **{k: v for k, v in assets.items() if k != "sentinel_close"}}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {TARGET} sha256={hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
