"""The weapon cels are reductions of vector illustrations: the committed
native sheets are exactly what `tools/draw_weapons.py` reduces from the SVGs,
and every sheet fills the weapon window with five distinct cels."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_rom as br  # noqa: E402
import draw_weapons  # noqa: E402


@unittest.skipUnless(br.SABLE_ART, "the legacy profile keeps its drawn cels")
class WeaponArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "assets" / "sable_v2" / "assets.json").read_text())

    def test_the_committed_sheets_are_the_reduction_of_their_illustrations(self):
        for name in draw_weapons.WEAPONS:
            record = self.manifest["assets"][name]
            data = draw_weapons.sheet_bytes(draw_weapons.render_sheet(name))
            path = ROOT / "assets" / "sable_v2" / record["file"]
            self.assertEqual(path.read_bytes(), data, f"{name}: regenerate with tools/draw_weapons.py --write")
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest(), name)
            self.assertEqual(record["frames"], draw_weapons.FRAMES, name)
            self.assertEqual(record["size"], [draw_weapons.CEL, draw_weapons.CEL], name)

    def test_every_weapon_fills_the_window_with_five_distinct_cels(self):
        from lupine3d_v4.sprite_assets import compile_sheet
        for name in draw_weapons.WEAPONS:
            sheet = compile_sheet(name, paired=True)
            self.assertEqual(len(sheet), br.WEAPON_TILE_BYTES, name)
            cels = [sheet[i * 256:(i + 1) * 256] for i in range(5)]
            self.assertEqual(len(set(cels)), 5, f"{name}: two cels are identical")
            for index, cel in enumerate(cels):
                self.assertNotEqual(cel, bytes(256), f"{name} cel {index} is empty")
        self.assertEqual(br.make_weapon_tiles(), compile_sheet("shotgun", paired=True))
        self.assertEqual(br.make_slug_tiles(), compile_sheet("slug_rifle", paired=True))

    def test_the_muzzle_sits_under_the_flash_and_the_gloves_in_their_objects(self):
        # The flash object covers cel columns 12..19 at the top; a muzzle
        # anywhere else would flash beside the barrel. The bottom corner
        # objects carry OBJ palette 5, so they are where the gloves are and
        # the only place leather may appear: they must hold ink in every cel.
        for name in draw_weapons.WEAPONS:
            for index, cel in enumerate(draw_weapons.render_sheet(name)):
                top = next(y for y in range(draw_weapons.CEL) if any(cel[y]))
                columns = [x for x in range(draw_weapons.CEL) if cel[top][x]]
                self.assertTrue(all(12 <= x <= 19 for x in columns), f"{name} cel {index}: apex at {columns}")
                for x0 in (0, 24):
                    ink = sum(cel[y][x] != 0 for y in range(16, 32) for x in range(x0, x0 + 8))
                    self.assertGreater(ink, 24, f"{name} cel {index}: the glove object at {x0} is nearly empty")


if __name__ == "__main__":
    unittest.main()
