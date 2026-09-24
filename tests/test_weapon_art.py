"""The weapon cels are rendered from 3D models: the committed native sheets
are exactly what the showcase's `games/sable_outpost/art/tools/render_weapons.py` renders, every sheet fills the
40x32 window with four distinct cels, and each weapon carries the OBJ
palette its objects were fitted to."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "games" / "sable_outpost" / "art"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ART / "tools"))
import build_rom as br  # noqa: E402


@unittest.skipUnless(br.SABLE_ART, "the legacy profile keeps its drawn cels")
class WeaponArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import render_weapons
        cls.rw = render_weapons
        cls.manifest = json.loads((ART / "sprites.json").read_text())
        cls.sheets = {name: render_weapons.render_sheet(name) for name in render_weapons.WEAPONS}

    def test_the_committed_sheets_are_the_render_of_their_models(self):
        for name, (indices, palettes) in self.sheets.items():
            record = self.manifest["assets"][name]
            data = self.rw.sheet_png(indices)
            path = ART / record["file"]
            self.assertEqual(path.read_bytes(), data, f"{name}: regenerate with games/sable_outpost/art/tools/render_weapons.py --write")
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest(), name)
            self.assertEqual(record["frames"], self.rw.FRAMES, name)
            self.assertEqual(record["size"], [self.rw.WIDTH, self.rw.HEIGHT], name)
            self.assertEqual(record["object_palettes"], palettes, name)

    def test_the_window_matches_the_engine(self):
        self.assertEqual(self.rw.WIDTH, br.WEAPON_COLUMNS * 8)
        self.assertEqual(len(self.rw.FRAMES), br.WEAPON_CELS)
        self.assertEqual(self.rw.WINDOW[0], br.WEAPON_SCREEN_X)
        self.assertEqual(self.rw.WINDOW[1], 120 - 32)

    def test_every_weapon_fills_the_window_with_four_distinct_cels(self):
        from lupine3d_v4.sprite_assets import compile_sheet
        size = br.WEAPON_CEL_PATTERNS * 16
        for name in self.rw.WEAPONS:
            sheet = compile_sheet(name, paired=True)
            self.assertEqual(len(sheet), br.WEAPON_TILE_BYTES, name)
            cels = [sheet[i * size:(i + 1) * size] for i in range(br.WEAPON_CELS)]
            self.assertEqual(len(set(cels)), br.WEAPON_CELS, f"{name}: two cels are identical")
            for index, cel in enumerate(cels):
                self.assertNotEqual(cel, bytes(size), f"{name} cel {index} is empty")
        self.assertEqual(br.make_weapon_tiles(), compile_sheet("shotgun", paired=True))
        self.assertEqual(br.make_slug_tiles(), compile_sheet("slug_rifle", paired=True))

    def test_the_muzzle_sits_under_the_flash(self):
        # The flash object covers world x 76..83 over the window's top rows;
        # the middle of the barrel where it leaves the window has to be
        # under it in every cel, or the gun flashes beside its muzzle. (The
        # barrel is cut by the window's edge at an angle, so the top row is
        # wider than the flash; its centre is what must line up.)
        flash = range(76 - self.rw.WINDOW[0], 84 - self.rw.WINDOW[0])
        for name, (indices, _) in self.sheets.items():
            for index, cel in enumerate(indices):
                top = next(y for y in range(self.rw.HEIGHT) if cel[y].any())
                columns = [x for x in range(self.rw.WIDTH) if cel[top][x]]
                centre = (min(columns) + max(columns)) // 2
                self.assertIn(centre, flash, f"{name} cel {index}: muzzle centred at {centre}")

    def test_the_rom_carries_each_weapons_object_palettes(self):
        rom, asm, _ = br.make_rom()
        table = asm.labels["weapon_object_attributes"]
        for weapon, name in enumerate(self.rw.WEAPONS):
            start = table + weapon * br.WEAPON_OBJECTS
            self.assertEqual(list(rom[start:start + br.WEAPON_OBJECTS]),
                             [0x08 | p for p in self.sheets[name][1]], name)


if __name__ == "__main__":
    unittest.main()
