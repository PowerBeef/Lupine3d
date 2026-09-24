"""Choosing the game a build makes, and starting a new one.

`LUPINE3D_GAME` (and `--game` on `build_rom.py` and `lupine`) names a game
directory or a game under games/; the showcase is the default and keeps
build/, any other game builds into build/games/<id>/. `lupine new-game`
copies a game with a new identity and without the source's goldens.
"""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import lupine  # noqa: E402
from lupine3d_v4.game import DEFAULT_GAME_DIR, GAMES, load_game, resolve_game_dir  # noqa: E402

SABLE = ROOT / "games" / "sable_outpost"


class GameSelectionTests(unittest.TestCase):
    def test_the_showcase_is_the_default_and_keeps_build(self):
        self.assertEqual(resolve_game_dir({}), DEFAULT_GAME_DIR)
        game = load_game(SABLE)
        self.assertTrue(game.is_showcase)
        self.assertEqual(game.build_dir(ROOT / "build"), ROOT / "build")

    def test_a_game_is_named_by_directory_or_by_its_name_under_games(self):
        self.assertEqual(resolve_game_dir({"LUPINE3D_GAME": "sable_outpost"}), SABLE.resolve())
        self.assertEqual(resolve_game_dir({"LUPINE3D_GAME": str(SABLE)}), SABLE.resolve())
        self.assertEqual(GAMES, ROOT / "games")

    def test_the_manifest_record_names_every_file_the_build_reads(self):
        record = load_game(SABLE).record()
        self.assertEqual((record["id"], record["directory"]), ("sable_outpost", "games/sable_outpost"))
        for name in ("game.json", "screens.json", "art/sprites.json", "audio/sound.json",
                     "levels/living_world.json", "textures/steel_panel.png", "art/native/fixtures.png"):
            self.assertIn(name, record["files"])
            self.assertRegex(record["files"][name], r"^[0-9a-f]{64}$")
        # Playtests drive the built ROM; they are not build inputs.
        self.assertFalse(any(name.startswith("playtests/") for name in record["files"]))

    def test_the_game_option_reaches_the_environment_before_the_engine_is_imported(self):
        import build_rom
        saved = os.environ.get("LUPINE3D_GAME")
        try:
            build_rom._select_game(["--output-dir", "x", "--game", "games/example"])
            self.assertEqual(os.environ["LUPINE3D_GAME"], "games/example")
            build_rom._select_game(["--game=games/other"])
            self.assertEqual(os.environ["LUPINE3D_GAME"], "games/other")
        finally:
            if saved is None:
                os.environ.pop("LUPINE3D_GAME", None)
            else:
                os.environ["LUPINE3D_GAME"] = saved

    def test_every_game_facing_command_takes_the_game_option(self):
        parser = lupine.build_parser()
        for command in (["build"], ["run"], ["snapshot"], ["level", "check", "x.json"], ["game", "check"],
                        ["profile"], ["witnesses"], ["sable-check"], ["symbols"]):
            args = parser.parse_args(command + ["--game", "games/example"])
            self.assertEqual(args.game, "games/example", command)

    def test_new_game_copies_a_game_with_its_own_identity_and_no_goldens(self):
        with tempfile.TemporaryDirectory() as scratch:
            destination = Path(scratch) / "night_shift"
            saved = os.environ.get("LUPINE3D_GAME")
            try:
                with redirect_stdout(io.StringIO()) as out:
                    status = lupine.main(["new-game", str(destination), "--from", str(SABLE)])
            finally:
                if saved is None:
                    os.environ.pop("LUPINE3D_GAME", None)
                else:
                    os.environ["LUPINE3D_GAME"] = saved
            self.assertEqual(status, 0, out.getvalue())
            game = load_game(destination)
            self.assertEqual((game.id, game.title, game.rom_title, game.rom_version),
                             ("night_shift", "Night Shift", "NIGHT SHIFT", 0))
            self.assertEqual(game.profiles, ("slim",))
            self.assertFalse(game.is_showcase)
            self.assertEqual(game.build_dir(ROOT / "build"), ROOT / "build" / "games" / "night_shift")
            self.assertFalse((destination / "snapshots").exists())
            self.assertEqual(game.level_paths[0].name, "living_world.json")
            self.assertIn("lupine.py build --game", out.getvalue())
            # A second scaffold into a directory that is not empty is refused.
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(lupine.main(["new-game", str(destination), "--from", str(SABLE)]), 1)
            self.assertIn("not empty", out.getvalue())

    def test_only_the_showcase_builds_the_historical_profiles(self):
        with tempfile.TemporaryDirectory() as scratch:
            destination = Path(scratch) / "copy"
            with redirect_stdout(io.StringIO()):
                lupine.main(["new-game", str(destination), "--from", str(SABLE)])
            manifest = json.loads((destination / "game.json").read_text())
            manifest["profiles"] = ["slim", "compact"]
            (destination / "game.json").write_text(json.dumps(manifest))
            env = {k: v for k, v in os.environ.items() if not k.startswith("LUPINE3D_")}
            env.update(LUPINE3D_GAME=str(destination), LUPINE3D_DISPLAY="compact")
            result = subprocess.run([sys.executable, "-c", "import lupine3d_v4.layout"], cwd=ROOT / "tools",
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("build only the showcase", result.stderr)


if __name__ == "__main__":
    unittest.main()
