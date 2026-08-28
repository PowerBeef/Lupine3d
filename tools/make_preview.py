#!/usr/bin/env python3
"""Render current Living World still and GIF previews."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as v2  # noqa: E402
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


def main() -> None:
    v2_rom, v2_assembler, _ = v2.make_rom()
    v2.BUILD.mkdir(parents=True, exist_ok=True)

    cgb = CGB(v2_rom, v2_assembler.labels)
    cgb.button_provider = preview_input
    frames: list[Image.Image] = []
    for target in range(1, 31):
        cgb.run(until_swaps=target, max_steps=6_000_000)
        raw = cgb.render_screen()
        frames.append(nearest(raw))

    # A separate authored pose makes the main project image describe the
    # current engine: wall composition, the 16x32 Sentinel and foreground UI.
    hero = CGB(v2_rom, v2_assembler.labels)
    hero.run(until_pc=v2_assembler.labels["main_loop"], max_steps=2_000_000)
    hero.write16(v2.PLAYER_XL, 0x0C80)
    hero.write16(v2.PLAYER_YL, 0x0D80)
    hero.write8(v2.ANGLE, 0)
    hero.run(until_swaps=1, max_steps=3_000_000)
    hero_image = nearest(hero.render_screen())

    still_path = v2.BUILD / "lupine3d_preview_4x.png"
    docs_still_path = ROOT / "docs" / "images" / "lupine3d_preview_4x.png"
    gif_path = v2.BUILD / "lupine3d_preview.gif"
    hero_image.save(still_path, optimize=True)
    hero_image.save(docs_still_path, optimize=True)
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

    print(f"Wrote {still_path}")
    print(f"Wrote {docs_still_path}")
    print(f"Wrote {gif_path}")


if __name__ == "__main__":
    main()
