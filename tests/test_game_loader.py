"""The game loader: what it derives from a manifest, and what it refuses.

A creator meets the engine first through the loader's messages, so each
refusal is pinned here with the words it uses: the file and the key, what is
wrong, and (for a limit) the engine fact behind it. The cases run against a
copy of the showcase with one thing broken at a time.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from lupine3d_v4.game import GameError, KEYS, load_game  # noqa: E402
from lupine3d_v4.limits import LIMITS  # noqa: E402

SABLE = ROOT / "games" / "sable_outpost"


def edit(file: str, change):
    """A case's mutation: load `file` as JSON, change it, write it back."""
    def apply(root: Path) -> None:
        path = root / file
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return apply


def game(change):
    return edit("game.json", change)


def screens(change):
    return edit("screens.json", change)


def set_key(path: list, value):
    def change(data):
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return change


def delete_key(path: list):
    def change(data):
        target = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
    return change


def more_levels(data):
    episodes = data["episodes"]
    for n in range(LIMITS["levels"].maximum + 1 - sum(len(e["levels"]) for e in episodes)):
        episodes[-1]["levels"].append(f"levels/extra_{n}.json")


def add_level_files(root: Path) -> None:
    source = root / "levels" / "living_world.json"
    for n in range(8):
        shutil.copy(source, root / "levels" / f"extra_{n}.json")


def fourth_episode(data):
    last = data["episodes"][-1]
    last["closing"] = "episode_three_closing"
    data["episodes"].append({"name": "Four", "levels": [last["levels"].pop()], "opening": "episode_four_opening"})


def extra_theme(count):
    def change(data):
        while len(data["themes"]) < count:
            theme = json.loads(json.dumps(data["themes"][0]))
            theme["name"] = f"extra_{len(data['themes'])}"
            data["themes"].append(theme)
    return change


def extra_kind(data):
    data["kinds"].append(dict(data["kinds"][0], name="fifth"))


def extra_texture(data):
    data["textures"]["eighth"] = "textures/steel_panel.png"


def small_line(**fields):
    """The game over screen's first line as 3x5 text, with `fields` changed."""
    def change(data):
        data["screens"]["gameover"][0] = dict({"text": "LUPINE", "y": 20, "colour": 2, "scale": 3}, **fields)
    return change


def reading_line(**fields):
    def change(data):
        data["screens"]["gameover"][0].update(fields)
    return change


def drop_title_field(data):
    data["screens"]["title"]["lines"] = [line for line in data["screens"]["title"]["lines"] if "field" not in line]


def song_rows(rows):
    def change(data):
        for channel in ("pulse", "wave", "noise"):
            data[channel]["rows"] = rows(data[channel]["rows"])
    return change


def too_long(rows):
    steps = "".join(rows)
    steps = (steps * (LIMITS["song_rows"].maximum // len(steps) + 2))[:LIMITS["song_rows"].maximum + 1]
    return [steps]


# (case, mutation, the words the refusal must contain)
CASES = [
    ("unknown key", game(set_key(["kindz"], [])), r"game\.json: the manifest has an unknown key 'kindz'; did you mean 'kinds'\?"),
    ("missing key", game(delete_key(["weapons"])), r"the manifest is missing 'weapons'"),
    ("format", game(set_key(["format"], "lupine-game-v0")), r"format is 'lupine-game-v0'; this engine reads 'lupine-game-v1'"),
    ("id", game(set_key(["id"], "Bad-Id")), r"id 'Bad-Id' must be lower-case letters, digits and underscores"),
    ("profiles", game(set_key(["profiles"], ["wide"])), r"profiles must be a non-empty list drawn from slim, compact, legacy"),
    ("path leaves the game", game(set_key(["episodes", 0, "levels", 0], "../sable_outpost/levels/living_world.json")),
     r"episodes\[0\]\.levels\[0\] '\.\./sable_outpost/levels/living_world\.json' leaves the game directory"),
    ("missing file", game(set_key(["episodes", 0, "levels", 0], "levels/nope.json")),
     r"episodes\[0\]\.levels\[0\] 'levels/nope\.json' does not exist"),
    ("level twice", game(lambda d: d["episodes"][1]["levels"].append(d["episodes"][0]["levels"][0])),
     r"level living_world\.json appears twice in the campaign"),
    ("too many levels", game(more_levels), r"episodes: 21 levels in the campaign is more than the engine's 20: levels pack five"),
    ("too many episodes", game(fourth_episode), r"episodes: 4 episodes is more than the engine's 3"),
    ("prologue without a screen", game(set_key(["episodes", 0, "opening"], "x")),
     r"screens\.json has no 'x' screen \(an episode names it\)"),
    ("later episode without opening", game(delete_key(["episodes", 1, "opening"])),
     r"episodes\[1\] needs an 'opening' screen"),
    ("too many kinds", game(extra_kind), r"kinds: 5 enemy kinds is more than the engine's 4: an actor's kind is two bits"),
    ("kind palette", game(set_key(["kinds", 0, "palette"], "neon")),
     r"kinds\[0\]\.palette 'neon' is not one of the actor_palettes \(sentinel, warden, skirmisher\)"),
    ("kind drop", game(set_key(["kinds", 0, "drop"], "ammo")), r"kinds\[0\]\.drop 'ammo' must be one of medkit, keycard"),
    ("contact damage", game(set_key(["kinds", 0, "contact_damage"], 171)),
     r"kinds\[0\]\.contact_damage must be a whole number from 0 to 170"),
    ("kind names", game(set_key(["kinds", 1, "name"], "sentinel")), r"kind names must be distinct"),
    ("weapon count", game(lambda d: d["weapons"].pop()), r"weapons must list exactly 4 weapons"),
    ("first weapon", game(set_key(["weapons", 0, "from_level"], 2)), r"weapons\[0\]\.from_level must be 1"),
    ("weapon order", game(set_key(["weapons", 2, "from_level"], 20)), r"weapons must be listed in the order the player gets them"),
    ("too many themes", game(extra_theme(5)), r"themes: 5 themes is more than the engine's 4"),
    ("theme texture", game(set_key(["themes", 0, "textures", "structure"], "marble")),
     r"themes\[0\]\.textures\.structure 'marble' is not in textures"),
    ("unused texture", game(set_key(["themes", 0, "textures", "machinery"], "steel_panel")),
     r"texture 'machinery_grille' is not used by any theme"),
    ("too many textures", game(extra_texture), r"textures: 8 wall textures is more than the engine's 7"),
    ("door texture on walls", game(set_key(["themes", 0, "textures", "door"], "steel_panel")),
     r"texture 'steel_panel' is used both on doors and on walls"),
    ("colour", game(set_key(["themes", 0, "colours", "ceiling"], [32, 0, 0])),
     r"themes\[0\]\.colours\.ceiling must be \[red, green, blue\] with each from 0 to 31"),
    ("rom header", game(set_key(["rom", "header_title"], "lupine")), r"rom\.header_title must be at most 15 upper-case letters"),
    ("hud word length", game(set_key(["hud", "words", "hunt"], "HUNTS")),
     r"hud\.words\.hunt 'HUNTS': 5 characters in a HUD word is more than the engine's 4"),
    ("hud word glyph", game(set_key(["hud", "words", "caption"], "GO#")), r"hud\.words\.caption 'GO#' uses '#', which the 3x5 caption font lacks"),
    ("sprite record", game(set_key(["sprites", "reticle"], "crosshair")), r"sprites\.reticle 'crosshair' is not a record of sprites\.json"),
    ("fixture kinds", game(set_key(["fixture_kinds"], ["vent", "light", "access"])),
     r"fixture_kinds must name the 4 wall fixture families"),
    ("playtests need a tour", game(delete_key(["playtests", "tour"])), r"playtests is missing 'tour'"),
    ("preview", game(set_key(["preview", "x"], 70)), r"preview\.x must be a position in cells, above 0 and below 64"),
    ("screen glyph", screens(small_line(text="LUPINE~")), r"screens\.json gameover\[0\] 'LUPINE~' uses '~', which the screen font does not have"),
    ("screen width", screens(small_line(text="LUPINE THREE D")), r"screens\.json gameover\[0\] 'LUPINE THREE D' is 168 pixels wide at scale 3; a line fits 152"),
    ("screen frame", screens(small_line(y=130)), r"screens\.json gameover\[0\] at y=130, scale 3, leaves the frame"),
    ("reading glyph", screens(reading_line(say="SIGNAL LOST~")), r"screens\.json gameover\[0\] 'SIGNAL LOST~' uses '~', which the reading face does not have"),
    ("reading width", screens(reading_line(say="THE SIGNAL IS LOST NOW")),
     r"screens\.json gameover\[0\] 'THE SIGNAL IS LOST NOW' needs 22 columns and a framed screen has 18"),
    ("reading row", screens(reading_line(row=17)), r"screens\.json gameover\[0\] is on row 17; a framed screen's reading-face rows are 1-16"),
    ("image kind", screens(set_key(["screens", "gameover", 0], {"image": "screens.json", "row": 2})),
     r"screens\.json gameover\[0\]\.image must be an indexed PNG"),
    ("debrief count", screens(lambda d: d["debriefs"].pop()), r"screens\.json debriefs must list one screen per level but the last: 17"),
    ("missing screen", screens(delete_key(["screens", "gameover"])), r"screens\.json has no 'gameover' screen"),
    ("extra screen", screens(set_key(["screens", "credits"], [{"text": "HI", "y": 20, "colour": 1}])),
     r"screens\.json screen 'credits' is never shown"),
    ("screen fields", screens(drop_title_field),
     r"screens\.json screen 'title' has fields none; the engine writes skill there"),
    ("song channels", edit("audio/title.json", lambda d: d["noise"]["rows"].pop()),
     r"title\.json: the three channels must have the same number of rows"),
    ("song rows", edit("audio/title.json", song_rows(too_long)), r"title\.json has 1323 rows; a song holds 1 to 1322"),
    ("note", edit("audio/title.json", set_key(["pulse", "notes", "a"], "H4")), r"title\.json pulse\.notes 'a' 'H4' is not a note from C2 to D#7"),
    ("sound effects", edit("audio/sound.json", delete_key(["effects", "shoot"])), r"sound\.json effects is missing 'shoot'"),
]


class GameLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.root = Path(cls.scratch.name) / "game"
        shutil.copytree(SABLE, cls.root, ignore=shutil.ignore_patterns(
            "snapshots", "masters", "previews", "history", "tools", "__pycache__"))
        add_level_files(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_trimmed_copy_loads(self):
        self.assertEqual(load_game(self.root).id, "sable_outpost")

    def test_every_refusal_names_the_problem(self):
        files = sorted(p for p in self.root.rglob("*.json"))
        originals = {path: path.read_bytes() for path in files}
        for name, mutate, message in CASES:
            with self.subTest(name):
                try:
                    mutate(self.root)
                    with self.assertRaisesRegex(GameError, message):
                        load_game(self.root)
                finally:
                    for path, data in originals.items():
                        path.write_bytes(data)

    def test_a_directory_without_a_manifest_or_with_bad_json(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(GameError, "no game.json"):
                load_game(Path(empty))
            (Path(empty) / "game.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(GameError, "not valid JSON"):
                load_game(Path(empty))

    def test_the_showcase_derives_the_engine_constants_it_always_had(self):
        sable = load_game(SABLE)
        self.assertEqual(sable.episode_lengths, (6, 6, 6))
        self.assertEqual(sable.episode_starts, (6, 12))
        self.assertEqual(sable.kind_ids, {"sentinel": 0, "skirmisher": 1, "warden": 2, "boss": 3})
        self.assertEqual(sable.theme_ids, {"outpost": 0, "reactor": 1, "spire": 2})
        self.assertEqual(sable.texture_names, ("steel_panel", "machinery_grille", "door_plate", "reactor_plate",
                                               "reactor_pipes", "spire_hull", "spire_array"))
        self.assertEqual(sable.texture_sets, ((0, 1, 2), (3, 4, 2), (5, 6, 2)))
        self.assertEqual([w.from_level for w in sable.weapons], [1, 1, 7, 13])
        self.assertEqual(sable.episode_screen_names, ("episode_one_closing", "episode_two_closing", "episode_one_opening",
                                                      "episode_two_opening", "episode_three_opening"))
        self.assertEqual(sable.opening_starts, (0, 6, 12))
        self.assertEqual(sable.debriefs, 17)
        self.assertEqual(list(sable.songs), ["title", "world", "victory", "gameover", "ending", "reactor", "spire", "overseer"])

    def test_the_starter_is_a_complete_small_game(self):
        starter = load_game(ROOT / "games" / "starter")
        self.assertEqual((starter.id, starter.title, starter.rom_title), ("starter", "Starter", "STARTER"))
        self.assertEqual(starter.episode_lengths, (2,))
        self.assertEqual(starter.episode_starts, ())
        self.assertEqual(starter.episode_screen_names, ())
        self.assertEqual(starter.kind_ids, {"drone": 0, "carrier": 1})
        self.assertEqual([kind.drop for kind in starter.kinds], ["medkit", "keycard"])
        self.assertEqual([w.from_level for w in starter.weapons], [1, 1, 2, None])
        self.assertEqual(starter.theme_ids, {"training": 0})
        self.assertEqual(set(starter.playtests), {"tour"})
        self.assertFalse(starter.is_showcase)
        # Everything it builds from is inside its own folder, so the folder can be copied.
        for relative in starter.files:
            self.assertTrue((starter.root / relative).is_file(), relative)

    def test_the_key_table_covers_every_object_the_loader_reads(self):
        self.assertEqual(set(KEYS), {
            "game", "episode", "kind", "weapon", "theme", "theme.textures", "theme.colours", "shared_palettes", "rom",
            "audio", "audio.songs", "hud", "hud.words", "sprites", "playtests", "preview", "screens", "screen",
            "screen.text", "screen.field", "screen.say", "screen.say_field", "screen.image", "song", "song.channel", "sound", "sound.instruments", "sound.pulse", "sound.wave",
            "sound.noise", "sound.effects"})
        for name, (allowed, required) in KEYS.items():
            self.assertLessEqual(required, allowed, name)


if __name__ == "__main__":
    unittest.main()
