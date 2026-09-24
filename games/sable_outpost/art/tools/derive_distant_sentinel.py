#!/usr/bin/env python3
"""The Sentinel's distant cels: the far sheet at quarter scale. Never called by ROM builds.

The near cel is 16x32 and the far cel 8x16, an exact half; this sheet is the
next half, a 4x8 figure centred at the foot of an 8x16 canvas so the engine
draws it as one 8x16 object exactly like the far cel. Each 2x2 block of the
far cel becomes one pixel: transparent unless two or more of its pixels are
inked, the visor highlight (index 3) where the block has one, else the
commonest ink. The result is indexed native art, committed as a source asset
and recorded in ../sprites.json; `--check` verifies the committed sheet is
exactly what this derivation produces.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ART = Path(__file__).resolve().parents[1]
SOURCE = ART / "native" / "sentinel_far.png"
TARGET = ART / "native" / "sentinel_distant.png"


def derive() -> Image.Image:
    far = Image.open(SOURCE)
    width, height = far.size
    frames = width // 8
    assert height == 16 and width % 8 == 0, far.size
    out = Image.new("P", (frames * 8, 16), 0)
    out.putpalette(far.getpalette())
    out.info["transparency"] = 0
    for frame in range(frames):
        for y in range(8):
            for x in range(4):
                block = [far.getpixel((frame * 8 + 2 * x + dx, 2 * y + dy)) for dy in (0, 1) for dx in (0, 1)]
                inked = [value for value in block if value]
                if len(inked) >= 2:
                    value = 3 if 3 in inked else Counter(inked).most_common(1)[0][0]
                    out.putpixel((frame * 8 + 2 + x, 8 + y), value)
    return out


def encoded(image: Image.Image) -> bytes:
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer, format="PNG", transparency=0, optimize=False)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the committed sheet and its manifest record")
    args = parser.parse_args()
    data = encoded(derive())
    record = json.loads((ART / "sprites.json").read_text())["assets"]["sentinel_distant"] if args.check else None
    if args.check:
        committed = TARGET.read_bytes()
        if committed != data:
            sys.exit(f"{TARGET.name} differs from its derivation; rerun without --check")
        if record["sha256"] != hashlib.sha256(committed).hexdigest():
            sys.exit("sprites.json records a different sentinel_distant hash")
        print(f"{TARGET.name} matches its derivation")
        return
    TARGET.write_bytes(data)
    print(f"wrote {TARGET} sha256={hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
