#!/usr/bin/env python3
"""Reduce the vector weapon illustrations to the native 32x32 cel sheets.

    python tools/draw_weapons.py                 # preview sheet under build/
    python tools/draw_weapons.py --write         # write the native PNGs and their hashes
    python tools/draw_weapons.py --check         # the committed PNGs equal a fresh reduction

Offline authoring, never called by a ROM build: the build compiles the
committed indexed PNGs under `assets/sable_v2/native/` through
`sprite_assets`, exactly as it does the enemy and HUD art.

Each weapon is an SVG illustration under `assets/sable_v2/vector/`, drawn
in cel coordinates (`viewBox="0 0 32 32"`) with as much detail as the artist
likes, using only the weapon palette's three tones as fills (`#1e2328`
dark, `#6f8489` mid, `#eee5c5` light; anything else is an error). The
illustration carries named groups the cels are posed from: `action` (the
pump, charging handle, capacitor ring or vents, translated along the
gun), `flare` (shown in the kick cel only) and `gun` (everything, kicked
down and toward the eye on recoil). Each cel is rasterised at sixteen
times the cel size with cairosvg and reduced block by block: a cel pixel
is opaque when half its block is covered, dark when dark ink reaches a
quarter of it, mid when mid ink reaches a third, and otherwise the
majority tone. So a line drawn 0.5 cel units wide survives as a one-pixel
line and a highlight has to be at least half a cel unit wide to show.

Five cels per weapon, in the order the animation expects: idle, the kick,
the action back, the action returning, and settling. The bottom corner
objects of the weapon grid use OBJ palette 5 (leather), which is where the
gloves are drawn; the muzzle sits under the flash object at the top centre.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "assets" / "sable_v2" / "native"
VECTOR = ROOT / "assets" / "sable_v2" / "vector"
MANIFEST = ROOT / "assets" / "sable_v2" / "assets.json"

CEL = 32
SCALE = 16
STEEL = [(0, 0, 0), (30, 35, 40), (111, 132, 137), (238, 229, 197)]
LEATHER = [(0, 0, 0), (24, 24, 24), (107, 66, 41), (181, 132, 82)]
TONES = {"#1e2328": 1, "#6f8489": 2, "#eee5c5": 3}
TICKS = [0, 4, 6, 6, 8]
FRAMES = ["idle", "recoil", "action_back", "action_forward", "recovery"]
SVG_NS = "http://www.w3.org/2000/svg"

# Per cel: how far the gun kicks (0..1) and how far the action travels (0..1).
POSES = (
    dict(recoil=0.0, action=0.0),
    dict(recoil=1.0, action=0.0, flare=True),
    dict(recoil=0.5, action=1.0),
    dict(recoil=0.25, action=0.45),
    dict(recoil=-0.15, action=0.0),
)
WEAPONS = ("shotgun", "slug_rifle", "arc_lance", "pulse_carbine")


def load(name: str) -> ET.ElementTree:
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(VECTOR / f"{name}.svg")
    root = tree.getroot()
    if root.get("viewBox") != f"0 0 {CEL} {CEL}":
        raise ValueError(f"{name}.svg: draw in cel coordinates, viewBox 0 0 {CEL} {CEL}")
    for element in root.iter():
        for attribute in ("fill", "stroke"):
            value = element.get(attribute)
            if value and value != "none" and value.lower() not in TONES:
                raise ValueError(f"{name}.svg: {attribute} {value!r} is not one of the three weapon tones")
    return tree


def pose(tree: ET.ElementTree, spec: dict) -> bytes:
    """The SVG bytes of one cel: the action translated, the flare shown or
    hidden, the whole gun kicked down and toward the eye."""
    root = tree.getroot()
    groups = {element.get("id"): element for element in root.iter(f"{{{SVG_NS}}}g") if element.get("id")}
    recoil, action = spec.get("recoil", 0.0), spec.get("action", 0.0)
    if "action" in groups:
        travel = float(groups["action"].get("data-travel", "3"))
        groups["action"].set("transform", f"translate(0,{action * travel:.3f})")
    if "flare" in groups:
        groups["flare"].set("display", "inline" if spec.get("flare") else "none")
    if "gun" in groups:
        grow = 1 + 0.06 * recoil
        groups["gun"].set("transform", f"translate(16,32) scale({grow:.4f}) translate(-16,-32) translate(0,{2.0 * recoil:.3f})")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def rasterise(svg: bytes) -> Image.Image:
    import cairosvg
    png = cairosvg.svg2png(bytestring=svg, output_width=CEL * SCALE, output_height=CEL * SCALE)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _tone(rgb) -> int:
    best = min(range(1, 4), key=lambda k: sum((a - b) ** 2 for a, b in zip(rgb, STEEL[k])))
    return best


def reduce(image: Image.Image) -> list[list[int]]:
    """Block-reduce the rasterised cel to 32x32 tone indices."""
    pixels = image.load()
    out = [[0] * CEL for _ in range(CEL)]
    for y in range(CEL):
        for x in range(CEL):
            counts = [0, 0, 0, 0]
            for sy in range(SCALE):
                for sx in range(SCALE):
                    r, g, b, a = pixels[x * SCALE + sx, y * SCALE + sy]
                    if a > 127:
                        counts[_tone((r, g, b))] += 1
            total = SCALE * SCALE
            if (counts[1] + counts[2] + counts[3]) * 2 < total:
                continue
            if counts[1] * 4 >= total:
                out[y][x] = 1
            elif counts[2] * 3 >= total:
                out[y][x] = 2
            else:
                out[y][x] = max((1, 2, 3), key=lambda k: counts[k])
    return out


def render_sheet(name: str) -> list[list[list[int]]]:
    tree = load(name)
    return [reduce(rasterise(pose(tree, spec))) for spec in POSES]


def sheet_image(cels) -> Image.Image:
    image = Image.new("P", (CEL * len(cels), CEL))
    image.putpalette([c for rgb in STEEL for c in rgb] + [0] * (768 - 12))
    for i, cel in enumerate(cels):
        for y in range(CEL):
            for x in range(CEL):
                image.putpixel((i * CEL + x, y), cel[y][x])
    return image


def sheet_bytes(cels) -> bytes:
    buffer = io.BytesIO()
    sheet_image(cels).save(buffer, format="PNG", transparency=0)
    return buffer.getvalue()


def preview(sheets, path: Path, scale: int = 6) -> None:
    """Every sheet stacked, with the bottom corner objects in leather."""
    rows, cols = len(sheets), max(len(c) for c in sheets)
    image = Image.new("RGB", (cols * (CEL + 2), rows * (CEL + 2)), (40, 40, 60))
    for r, cels in enumerate(sheets):
        for c, cel in enumerate(cels):
            for y in range(CEL):
                for x in range(CEL):
                    v = cel[y][x]
                    if v:
                        palette = LEATHER if (y >= 16 and (x < 8 or x >= 24)) else STEEL
                        image.putpixel((c * (CEL + 2) + x, r * (CEL + 2) + y), palette[v])
    image.resize((image.width * scale, image.height * scale), Image.NEAREST).save(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="write the native PNGs and update their manifest hashes")
    parser.add_argument("--check", action="store_true", help="fail unless the committed PNGs equal a fresh reduction")
    parser.add_argument("--weapon", action="append", choices=WEAPONS, help="only these weapons (default: all)")
    parser.add_argument("--preview", type=Path, default=ROOT / "build" / "weapons_preview.png")
    args = parser.parse_args(argv)
    names = args.weapon or WEAPONS
    sheets = {name: render_sheet(name) for name in names}
    manifest = json.loads(MANIFEST.read_text())
    status = 0
    for name, cels in sheets.items():
        data = sheet_bytes(cels)
        digest = hashlib.sha256(data).hexdigest()
        record = manifest["assets"][name]
        path = ROOT / "assets" / "sable_v2" / record["file"]
        if args.write:
            path.write_bytes(data)
            record["sha256"] = digest
            print(f"wrote {path.relative_to(ROOT)} {digest[:12]}")
        elif args.check:
            same = path.exists() and path.read_bytes() == data and record["sha256"] == digest
            print(f"{name}: {'ok' if same else 'DIFFERS from the committed PNG or its hash'}")
            status |= 0 if same else 1
        else:
            print(f"{name}: {digest[:12]}")
    if args.write:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    preview(list(sheets.values()), args.preview)
    print(f"preview: {args.preview}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
