"""No current file points at a path the game/engine separation moved.

The showcase's levels, art, textures, scenarios and goldens moved into
games/sable_outpost, the engine's level fixtures into tests/levels, and the
offline art tools beside the art. Historical records (release notes, the
archive, milestones, retained research results and oracles) keep the paths
of their day; everything else must use the current ones.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ("docs/archive/", "milestones/", "research/results/", "games/sable_outpost/playtests/archive/",
              "RELEASE_NOTES.md", "tests/fixtures/", "tests/test_no_stale_paths.py", ".render-baselines/")
TEXT = {".py", ".md", ".json", ".yml", ".yaml", ".txt", ".toml", ".cfg", ""}
# Files whose paths are relative to a game directory (a game's own files, the
# tools and tests that write or edit one, and the handbook pages that teach a
# game's layout), where levels/ and playtests/ are the game's.
GAME_RELATIVE = ("games/", "tests/test_game_loader.py", "tests/test_game_selection.py", "tools/make_limits_game.py",
                 "docs/tutorials/", "docs/how-to/", "docs/reference/")
# (pattern, why, whether a game-relative file may use it). A moved path is one
# not preceded by a path segment, so games/sable_outpost/levels/ and
# tests/levels/ are fine.
STALE = [
    (re.compile(r"(?<![\w./-])levels/[a-z0-9_]+\.json"), "levels moved to games/<id>/levels/ or tests/levels/", True),
    (re.compile(r"(?<![\w./-])assets/sable_v2\b"), "the showcase's art moved to games/sable_outpost/art/", False),
    (re.compile(r"(?<![\w./-])assets/textures\b"), "textures moved to games/<id>/textures/", False),
    (re.compile(r"(?<![\w./-])playtests/"), "scenarios moved to games/<id>/playtests/", True),
    (re.compile(r"(?<![\w./-])snapshots/(slim|compact|legacy)-"), "goldens moved to games/<id>/snapshots/", False),
    (re.compile(r"(?<![\w./-])tools/(render_weapons|adapt_sable_art)\.py"),
     "the art tools moved to games/sable_outpost/art/tools/", False),
    (re.compile(r"(?<![\w./-])docs/(guide/|(?!README)[A-Z][A-Z0-9_]*\.md)"),
     "the handbook moved its pages (docs/README.md lists them)", False),
    (re.compile(r'"docs" / "(guide|(?!README)[A-Z][A-Z0-9_]*\.md)"'),
     "the handbook moved its pages (docs/README.md lists them)", False),
]


def tracked_files() -> list[Path]:
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout.split("\0")
    return [ROOT / name for name in listed
            if name and not name.startswith(HISTORICAL) and Path(name).suffix in TEXT and (ROOT / name).is_file()]


class NoStalePathTests(unittest.TestCase):
    def test_current_files_use_the_moved_paths(self):
        problems = []
        for path in tracked_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            relative = path.relative_to(ROOT).as_posix()
            for number, line in enumerate(text.splitlines(), 1):
                for pattern, reason, game_relative in STALE:
                    if game_relative and relative.startswith(GAME_RELATIVE):
                        continue
                    match = pattern.search(line)
                    if match:
                        problems.append(f"{path.relative_to(ROOT)}:{number}: {match.group(0)} ({reason})")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
