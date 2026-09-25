#!/usr/bin/env python3
"""A game at every game-level maximum at once, generated from the showcase.

`tools/lupine3d_v4/limits.py` states what a game can hold; this tool proves
the numbers hold together, because several of them share one budget (the
fixed half of bank 0 takes every theme's texture directory and every
episode's screen dispatch). It writes a copy of the showcase with the most
levels, episodes, themes, textures and kinds the table allows, the heaviest
contact damage, weapons that unlock one level at a time (each later unlock is
a compare in resident code), the most songs with one of them the most rows
(the songs share one bank, so those two maxima are proven together), a
debrief after every level, and sound effects with no zero byte (a zero is
emitted one byte shorter).

`make limits` writes it, builds it, and runs `--check` in a process that
builds that game: each episode's first level, the last level and a level in
the added theme are entered by continue code, as a player would, and walked
with every frame check.

    python tools/make_limits_game.py [--output build/limits-game]
    LUPINE3D_GAME=build/limits-game python tools/make_limits_game.py --check
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from lupine3d_v4.limits import LIMITS  # noqa: E402

SOURCE = ROOT / "games" / "sable_outpost"
GAME_ID = "limits"
EXTRA_THEME = "limit_extra"


def maximum(name: str) -> int:
    return LIMITS[name].maximum


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def generate(output: Path) -> dict:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(SOURCE, output, ignore=shutil.ignore_patterns(
        "snapshots", "masters", "previews", "history", "tools", "__pycache__"))
    manifest = json.loads((output / "game.json").read_text(encoding="utf-8"))
    manifest.update(id=GAME_ID, title="Engine Limits", profiles=["slim"])
    manifest["rom"] = {"header_title": "LIMITS", "version": 0}
    manifest.pop("preview", None)

    # Themes: add copies of the first until the table's maximum, recoloured.
    themes = manifest["themes"]
    while len(themes) < maximum("themes"):
        theme = json.loads(json.dumps(themes[0]))
        theme["name"] = EXTRA_THEME if len(themes) == 3 else f"{EXTRA_THEME}_{len(themes)}"
        theme["colours"]["ceiling"] = [2, 2, 4]
        theme["colours"]["floor"] = [6, 5, 4]
        themes.append(theme)
    assert len(manifest["textures"]) == maximum("textures"), "the showcase no longer uses every texture slot"

    # Levels: the showcase's, then copies in the added theme, in three episodes.
    levels = [level for episode in manifest["episodes"] for level in episode["levels"]]
    extra = 0
    while len(levels) < maximum("levels"):
        source = output / levels[extra % 6]
        data = json.loads(source.read_text(encoding="utf-8"))
        data["name"] = f"Limit Copy {extra + 1}"
        data["palette_profile"] = themes[3]["name"]
        name = f"levels/limit_copy_{extra + 1}.json"
        write_json(output / name, data)
        levels.append(name)
        extra += 1
    episodes = manifest["episodes"]
    assert len(episodes) == maximum("episodes"), "the showcase no longer has the most episodes"
    size, spare = divmod(len(levels), len(episodes))
    start = 0
    for index, episode in enumerate(episodes):
        count = size + (1 if index < spare else 0)
        episode["levels"] = levels[start:start + count]
        start += count

    # Kinds: the most, one with the heaviest contact damage.
    assert len(manifest["kinds"]) == maximum("kinds"), "the showcase no longer fields every kind"
    manifest["kinds"][-1]["contact_damage"] = maximum("contact_damage")
    # Weapons: one more each level, so every later weapon is its own compare.
    for index, weapon in enumerate(manifest["weapons"]):
        weapon["from_level"] = index + 1

    # Songs: the title the most rows the sequencer holds, and one-bar cuts of
    # the world song as level songs until the game has the most songs (full
    # copies would overflow the music bank the songs share).
    path = output / manifest["audio"]["songs"]["title"]
    song = json.loads(path.read_text(encoding="utf-8"))
    for channel in ("pulse", "wave", "noise"):
        steps = "".join(song[channel]["rows"])
        steps = (steps * (maximum("song_rows") // len(steps) + 1))[:maximum("song_rows")]
        song[channel]["rows"] = [steps[i:i + 16] for i in range(0, len(steps), 16)]
    write_json(path, song)
    bar = json.loads((output / manifest["audio"]["songs"]["world"]).read_text(encoding="utf-8"))
    bar["loop_row"] = 0
    for channel in ("pulse", "wave", "noise"):
        bar[channel]["rows"] = bar[channel]["rows"][:1]
    level_songs = manifest["audio"].setdefault("level_songs", {})
    while len(manifest["audio"]["songs"]) + len(level_songs) < maximum("songs"):
        name = f"limit_song_{len(level_songs) + 1}"
        write_json(output / "audio" / f"{name}.json", bar)
        level_songs[name] = f"audio/{name}.json"
    # Debriefs: one after every level but the last, as the loader requires.
    screens_path = output / manifest["screens"]
    screens = json.loads(screens_path.read_text(encoding="utf-8"))
    if "debriefs" in screens:
        while len(screens["debriefs"]) < len(levels) - 1:
            screens["debriefs"].append(screens["debriefs"][-1])
        write_json(screens_path, screens)
    # Sound effects: no zero register byte, each emitted as a two-byte load.
    sound_path = output / manifest["audio"]["sound"]
    sound = json.loads(sound_path.read_text(encoding="utf-8"))
    sound["effects"] = {name: [value if int(str(value), 0) else "0x01" for value in values]
                        for name, values in sound["effects"].items()}
    write_json(sound_path, sound)

    write_json(output / "game.json", manifest)
    return {"levels": len(levels), "episodes": len(episodes), "themes": len(themes),
            "textures": len(manifest["textures"]), "kinds": len(manifest["kinds"])}


def check() -> dict:
    """Run in a process that builds the limits game (LUPINE3D_GAME)."""
    import hashlib
    import build_rom as br
    from playthrough import enter_sector
    from playtest import validate_frame
    from sm83emu import CGB, parse_symbols, run_to_world
    if br.GAME.id != GAME_ID:
        raise SystemExit(f"--check runs on the limits game; LUPINE3D_GAME selects {br.GAME.id}")
    game = br.GAME
    counts = {"levels": len(game.level_paths), "episodes": len(game.episodes), "themes": len(game.themes),
              "textures": len(game.textures), "kinds": len(game.kinds), "songs": len(game.songs),
              "song_rows": max(len(song.pulse) for song in game.songs.values())}
    for name, count in counts.items():
        assert count == maximum(name), (name, count, maximum(name))
    rom_path = br.GAME_BUILD / "lupine3d.gb"
    manifest = json.loads((br.GAME_BUILD / "build_manifest.json").read_text())
    rom = rom_path.read_bytes()
    assert hashlib.sha256(rom).hexdigest() == manifest["sha256"], "build the limits game first"
    symbols = parse_symbols(br.GAME_BUILD / "lupine3d.sym")
    extra_theme = game.theme_ids[EXTRA_THEME]
    first_extra = next(index for index, level in enumerate(br.CAMPAIGN) if level.palette_profile == extra_theme)
    visited = sorted({0, *br.EPISODE_STARTS, first_extra, br.LEVEL_COUNT - 1})
    for level in visited:
        cgb = CGB(rom, symbols)
        if level:
            enter_sector(cgb, level)
        run_to_world(cgb)
        assert cgb.read8(br.LEVEL_INDEX) == level, (level, cgb.read8(br.LEVEL_INDEX))
        assert cgb.read8(br.PALETTE_SET) == br.CAMPAIGN[level].palette_profile, level
        br.select_reference_level(level)
        for _ in range(8):
            cgb.button_provider = lambda *_: 0x02          # turn left: new walls every frame
            cgb.run(until_presentations=cgb.presentations + 1, max_steps=3_000_000)
            validate_frame(cgb)
        cgb.button_provider = None
    br.select_reference_level(0)
    report = {"schema": "lupine3d.limits.v1", "rom_sha256": manifest["sha256"], "counts": counts,
              "levels_entered": visited, "fixed_half_bytes_free": 0x4000 - manifest["memory_budget"]["fixed_code_end"],
              "resident_free_bytes": manifest["memory_budget"]["resident_free_bytes"], "passed": True}
    (br.GAME_BUILD / "limits_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "limits-game")
    parser.add_argument("--check", action="store_true", help="enter and walk the built limits game")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check(), indent=2))
    else:
        counts = generate(args.output)
        print(f"wrote {args.output}: " + ", ".join(f"{count} {name}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
