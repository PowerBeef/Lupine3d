#!/usr/bin/env python3
"""Render current-version still/GIF previews and a v0.1 comparison."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as v2  # noqa: E402
import build_rom_v1 as v1  # noqa: E402
from sm83emu import CGB  # noqa: E402


def preview_input(iteration: int, _swaps: int) -> int:
    # Tour the starting corridor, turn, fire, and continue moving.
    if 2 <= iteration <= 6:
        return 0x04  # Up
    if 7 <= iteration <= 11:
        return 0x01  # Right
    if iteration == 12:
        return 0x10  # A
    if 14 <= iteration <= 18:
        return 0x04  # Up
    if 19 <= iteration <= 23:
        return 0x02  # Left
    if iteration == 25:
        return 0x10  # A
    if 27 <= iteration <= 30:
        return 0x08  # Down
    return 0


def nearest(image: Image.Image, scale: int = 4) -> Image.Image:
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def comparison_image(v1_image: Image.Image, v2_image: Image.Image) -> Image.Image:
    label_h = 20
    canvas = Image.new("RGB", (320, 144 + label_h), (12, 12, 15))
    canvas.paste(v1_image, (0, label_h))
    canvas.paste(v2_image, (160, label_h))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((5, 5), "v0.1.0 — 40 columns", font=font, fill=(240, 240, 240))
    draw.text((165, 5), "v0.4.0 — exact + faster", font=font, fill=(240, 240, 240))
    return canvas.resize((canvas.width * 3, canvas.height * 3), Image.Resampling.NEAREST)


def main() -> None:
    v2_rom, v2_assembler, _ = v2.make_rom()
    v1_rom, v1_assembler, _ = v1.make_rom()
    v2.BUILD.mkdir(parents=True, exist_ok=True)

    cgb = CGB(v2_rom, v2_assembler.labels)
    cgb.button_provider = preview_input
    frames: list[Image.Image] = []
    raw_frames: list[Image.Image] = []
    for target in range(1, 31):
        cgb.run(until_swaps=target, max_steps=6_000_000)
        raw = cgb.render_screen()
        raw_frames.append(raw)
        frames.append(nearest(raw))

    still_path = v2.BUILD / "lupine3d_preview_4x.png"
    gif_path = v2.BUILD / "lupine3d_preview.gif"
    frames[0].save(still_path, optimize=True)
    paletted = [frame.quantize(colors=64) for frame in frames]
    paletted[0].save(
        gif_path,
        save_all=True,
        append_images=paletted[1:],
        duration=150,
        loop=0,
        optimize=True,
        disposal=2,
    )

    old = CGB(v1_rom, v1_assembler.labels)
    old.button_provider = preview_input
    old.run(until_swaps=10, max_steps=6_000_000)
    compare_path = v2.BUILD / "lupine3d_v010_v040_comparison.png"
    comparison_image(old.render_screen(), raw_frames[9]).save(compare_path, optimize=True)

    print(f"Wrote {still_path}")
    print(f"Wrote {gif_path}")
    print(f"Wrote {compare_path}")


if __name__ == "__main__":
    main()
