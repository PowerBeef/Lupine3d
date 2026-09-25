"""The Tiled round trip: every authored level survives JSON -> TMX -> JSON unchanged."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from lupine3d_v4 import levels, tmx_import  # noqa: E402


class TmxRoundTripTests(unittest.TestCase):
    def test_every_authored_level_round_trips_exactly(self):
        paths = sorted((ROOT / "games" / "sable_outpost" / "levels").glob("*.json")) + sorted((ROOT / "tests" / "levels").glob("*.json"))
        self.assertEqual(len(paths), 22)
        for path in paths:
            with self.subTest(level=path.name):
                source = json.loads(path.read_text(encoding="utf-8"))
                restored = tmx_import.import_tmx(tmx_import.export_tmx(source))
                self.assertEqual(restored, source)
                # Key order matters to a reviewer's diff, not to the compiler.
                self.assertEqual(list(restored), list(source))

    def test_round_tripped_level_compiles_to_the_same_payload(self):
        for name in levels.CAMPAIGN_ORDER:
            path = ROOT / "games" / "sable_outpost" / "levels" / name
            with tempfile.TemporaryDirectory() as directory:
                tmx = Path(directory) / "level.tmx"
                back = Path(directory) / "level.json"
                tmx_import.export_file(path, tmx)
                tmx_import.import_file(tmx, back)
                original, restored = levels.compile_level(path), levels.compile_level(back)
                self.assertEqual(restored.header_bytes(), original.header_bytes(), name)
                self.assertEqual(restored.segment_table, original.segment_table, name)
                self.assertEqual(restored.surface_table, original.surface_table, name)
                self.assertEqual(restored.door_bytes(), original.door_bytes(), name)
                self.assertEqual(restored.fixtures, original.fixtures, name)
                self.assertEqual(restored.extras_bytes(), original.extras_bytes(), name)

    def test_tmx_is_a_tiled_map_at_32_pixel_cells(self):
        source = json.loads((ROOT / "games" / "sable_outpost" / "levels" / "living_world.json").read_text())
        root = ET.fromstring(tmx_import.export_tmx(source))
        self.assertEqual((root.get("orientation"), root.get("width"), root.get("tilewidth")), ("orthogonal", "16", "32"))
        layer = next(l for l in root.findall("layer") if l.get("name") == "materials")
        gids = [int(t) for t in layer.find("data").text.replace("\n", "").split(",") if t.strip()]
        self.assertEqual(gids[:16], [2] * 16)                      # material 1 is gid 2
        spawn = next(g for g in root.findall("objectgroup") if g.get("name") == "spawn").find("object")
        self.assertEqual((spawn.get("x"), spawn.get("y")), ("144", "432"))   # 1152/8, 3456/8
        self.assertIsNotNone(spawn.find("point"))
        names = {g.get("name") for g in root.findall("objectgroup")}
        self.assertEqual(names, {"spawn", "doors", "entities", "fixtures", "surfaces", "exit"})

    def test_unknown_keys_and_surfaces_survive(self):
        source = json.loads((ROOT / "games" / "sable_outpost" / "levels" / "living_world.json").read_text())
        source["surfaces"] = [{"x": 5, "y": 6, "side": "south", "profile": "machinery"}]
        source["designer_notes"] = {"author": "test", "revision": 3}
        restored = tmx_import.import_tmx(tmx_import.export_tmx(source))
        self.assertEqual(restored, source)

    def test_importer_refuses_misaligned_and_foreign_tiles(self):
        source = json.loads((ROOT / "games" / "sable_outpost" / "levels" / "living_world.json").read_text())
        text = tmx_import.export_tmx(source)
        with self.assertRaises(ValueError):
            tmx_import.import_tmx(text.replace('name="exit"', 'name="exit" ', 1).replace('x="320" y="416" width="32"', 'x="321" y="416" width="32"'))
        with self.assertRaises(ValueError):
            tmx_import.import_tmx(text.replace("2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,", "9,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,", 1))


if __name__ == "__main__":
    unittest.main()
