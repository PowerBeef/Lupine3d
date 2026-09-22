"""Per-episode palette sets: the level header names a set, the loader keeps
it in fixed WRAM, and every world entry uploads that set with the LCD off."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_rom as br  # noqa: E402
from lupine3d_v4 import levels  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402


def palette_set(rom: bytes, labels: dict, index: int) -> tuple[bytes, bytes]:
    base = labels["bg_palettes"] + index * 128
    return rom[base:base + 64], rom[base + 64:base + 128]


class PaletteSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    def test_the_table_holds_one_set_per_episode_name(self):
        self.assertEqual(br.PALETTE_SET_COUNT, 3)
        self.assertEqual(self.manifest["palette_sets"], 3)
        self.assertEqual(self.manifest["palette_set_names"], ["outpost", "reactor", "spire"])
        self.assertEqual(levels.PALETTE_IDS, {"outpost": 0, "reactor": 1, "spire": 2})
        # The OBJ half of set 0 keeps its historical label.
        self.assertEqual(self.asm.labels["obj_palettes"], self.asm.labels["bg_palettes"] + 64)
        sets = [palette_set(self.rom, self.asm.labels, i) for i in range(br.PALETTE_SET_COUNT)]
        self.assertEqual(len({bg for bg, _ in sets}), 3)
        self.assertEqual(len({obj for _, obj in sets}), 3)
        # What lives outside the world never changes colour between episodes:
        # BG 1 (the steel HUD, which the screens use), BG 7, the weapon,
        # the drops, the muzzle flash, the decor and the reticle.
        bg0, obj0 = sets[0]
        for bg, obj in sets[1:]:
            self.assertEqual(bg[8:16], bg0[8:16])
            self.assertEqual(bg[56:64], bg0[56:64])
            self.assertEqual(obj[0:8], obj0[0:8])
            self.assertEqual(obj[16:48], obj0[16:48])
            # The lower-half rule holds in every set: colour 0 of the lower
            # palettes is the floor, the upper palettes' colour 1.
            for upper, lower in ((0, 2), (3, 4), (5, 6)):
                self.assertEqual(bg[lower * 8:lower * 8 + 2], bg[upper * 8 + 2:upper * 8 + 4])
                self.assertEqual(bg[lower * 8 + 4:lower * 8 + 8], bg[upper * 8 + 4:upper * 8 + 8])

    def test_init_palettes_uploads_the_named_set_and_clamps_a_bad_byte(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self.assertEqual(cgb.read8(br.PALETTE_SET), br.CAMPAIGN[0].palette_profile)
        for index in range(br.PALETTE_SET_COUNT):
            cgb.write8(br.PALETTE_SET, index)
            cgb.call_subroutine("init_palettes", max_steps=100_000)
            bg, obj = palette_set(self.rom, self.asm.labels, index)
            self.assertEqual(bytes(cgb.bg_palette), bg, index)
            self.assertEqual(bytes(cgb.obj_palette), obj, index)
        # A power-on value past the table reads set 0, never past the ROM data.
        cgb.write8(br.PALETTE_SET, 0xC7)
        cgb.call_subroutine("init_palettes", max_steps=100_000)
        self.assertEqual((bytes(cgb.bg_palette), bytes(cgb.obj_palette)), palette_set(self.rom, self.asm.labels, 0))

    def test_every_world_entry_uploads_the_set_with_the_lcd_off(self):
        # enter_world: call lcd_off; call init_palettes; ... The screens own
        # only BG palette 1, so this call is what restores a level's look.
        entry = self.asm.labels["enter_world"]
        lcd_off, init = self.asm.labels["lcd_off"], self.asm.labels["init_palettes"]
        self.assertEqual(self.rom[entry:entry + 6], bytes((0xCD, lcd_off & 255, lcd_off >> 8, 0xCD, init & 255, init >> 8)))

    def test_the_loader_stores_the_header_set_a_level_names(self):
        source = json.loads((ROOT / "levels" / "living_world.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            for name, index in levels.PALETTE_IDS.items():
                path = Path(directory) / f"{name}.json"
                path.write_text(json.dumps(dict(source, palette_profile=name)))
                level = levels.compile_level(path)
                self.assertEqual(level.palette_profile, index)
                self.assertEqual(level.header_bytes()[3], index)
            path.write_text(json.dumps(dict(source, palette_profile="lunar")))
            with self.assertRaises(KeyError):
                levels.compile_level(path)
        # The loader copies header byte 3 straight into the fixed-WRAM scalar.
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self.assertEqual(cgb.read8(br.PALETTE_SET), br.CAMPAIGN[0].header_bytes()[3])


if __name__ == "__main__":
    unittest.main()
