#!/usr/bin/env python3
"""A still and a GIF of the built game, rendered by the host harness.

The still is filmed from the game's `preview` pose (game.json: a position in
cells and the angle byte); the showcase's still is also the README's hero
image. The GIF walks the first level's start. Both land in the game's build
directory; images are captures of the emitted ROM, never generated."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as v2  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402
from playtest import set_test_world_byte  # noqa: E402


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


def episode_strip(rom: bytes, labels: dict[str, int]) -> Image.Image:
    """Each episode's first level as a player enters it (by continue code),
    side by side at 2x: the spawn view or the view after turning right for
    eight updates, whichever shows more colours, so every theme is seen."""
    from playthrough import enter_sector
    views = []
    for start in (0, *v2.EPISODE_STARTS):
        cgb = CGB(rom, labels)
        if start:
            enter_sector(cgb, start)
        run_to_world(cgb)
        candidates = []
        for presses in (0, 8):
            cgb.button_provider = (lambda *_: 0x01) if presses else (lambda *_: 0)
            cgb.run(until_presentations=cgb.presentations + max(presses, 1), max_steps=30_000_000)
            image = cgb.render_screen()
            world = image.crop((0, 0, 160, v2.VIEW_HEIGHT))
            candidates.append((len(set(world.getdata())), -presses, image))
        views.append(max(candidates)[2])
    strip = Image.new("RGB", (160 * len(views) + 4 * (len(views) - 1), 144), (13, 17, 23))
    for index, image in enumerate(views):
        strip.paste(image, (index * 164, 0))
    return nearest(strip, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-image", help="also save the still as docs/images/NAME (any game)")
    parser.add_argument("--episodes", help="save each episode's first level, side by side, as docs/images/NAME")
    args = parser.parse_args()
    v2_rom, v2_assembler, _ = v2.make_rom()
    v2.GAME_BUILD.mkdir(parents=True, exist_ok=True)

    cgb = CGB(v2_rom, v2_assembler.labels)
    # The campaign holds the world behind a title screen, so the preview has
    # to start it before it can film anything.
    run_to_world(cgb)
    cgb.button_provider = preview_input
    frames: list[Image.Image] = []
    for target in range(1, 31):
        cgb.run(until_presentations=target, max_steps=6_000_000)
        raw = cgb.render_screen()
        frames.append(nearest(raw))

    # A separate authored pose makes the still describe the game: the
    # showcase stands beside the comms room's vent wall facing the Sentinel,
    # so its hero image shows textured walls near and far, an enemy and the
    # HUD, not an empty start wall.
    hero = CGB(v2_rom, v2_assembler.labels)
    run_to_world(hero)
    if v2.GAME.preview is not None:
        x_q8, y_q8, angle = v2.GAME.preview
        for address, value in ((v2.PLAYER_XL, x_q8 & 0xFF), (v2.PLAYER_XH, x_q8 >> 8),
                               (v2.PLAYER_YL, y_q8 & 0xFF), (v2.PLAYER_YH, y_q8 >> 8), (v2.ANGLE, angle)):
            set_test_world_byte(hero, address, value)
    hero.run(until_presentations=1, max_steps=3_000_000)
    hero_image = nearest(hero.render_screen())

    still_path = v2.GAME_BUILD / "lupine3d_preview_4x.png"
    gif_path = v2.GAME_BUILD / "lupine3d_preview.gif"
    hero_image.save(still_path, optimize=True)
    written = [still_path, gif_path]
    if v2.GAME.is_showcase:
        docs_still_path = ROOT / "docs" / "images" / "lupine3d_preview_4x.png"
        hero_image.save(docs_still_path, optimize=True)
        written.insert(1, docs_still_path)
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

    if args.docs_image:
        path = ROOT / "docs" / "images" / args.docs_image
        hero_image.save(path, optimize=True)
        written.append(path)
    if args.episodes:
        path = ROOT / "docs" / "images" / args.episodes
        episode_strip(v2_rom, v2_assembler.labels).save(path, optimize=True)
        written.append(path)
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
