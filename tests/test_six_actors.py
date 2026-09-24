"""Six simulated actor slots: the loader, the AI loop, the draw pass and the
HUD count all run over MAX_ACTORS, and admission still bounds what is drawn."""
from pathlib import Path
import sys
import tempfile
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_rom as br  # noqa: E402
from lupine3d_v4 import levels  # noqa: E402
from playtest import set_test_world_byte, oam_budget  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402


class SixActorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    def test_the_layout_holds_six_slots_and_the_copy_carries_them(self):
        self.assertEqual(br.MAX_ACTORS, 6)
        self.assertEqual(br.ACTOR_DEPTHS, br.ENTITY_SLOTS + 96)
        self.assertLess(br.ACTOR_PASS, br.MASK_TILES)
        self.assertEqual(dict(br.WORLD_COPY_RANGES)[br.ENTITY_SLOTS], 96)
        self.assertEqual(br.WORLD_COPY_BYTES, 256 + 8 + br.WORLD_WINDOW_BYTES + 96)
        self.assertEqual(self.manifest["actor_slot_capacity"], 6)
        self.assertEqual(br.LEVEL_ACTOR_OFFSET + 96, br.LEVEL_FIXTURE_OFFSET)

    def test_a_level_may_field_six_actors_and_the_compiler_refuses_seven(self):
        source = json.loads((ROOT / "games" / "sable_outpost" / "levels" / "cryo_vault.json").read_text())
        walkable = [(x, y) for y, row in enumerate(source["rows"]) for x, cell in enumerate(row) if cell == "0"]
        spawn = (source["player_spawn"]["x_q8"] >> 8, source["player_spawn"]["y_q8"] >> 8)
        far = sorted(walkable, key=lambda c: -(abs(c[0] - spawn[0]) + abs(c[1] - spawn[1])))
        extra = [{"kind": "sentinel", "x_q8": x * 256 + 128, "y_q8": y * 256 + 128, "health": 3,
                  "activation_radius_q4": 64} for x, y in far[:3]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "six.json"
            six = dict(source, entities=source["entities"][:3] + extra)
            path.write_text(json.dumps(six))
            level = levels.compile_level(path)
            self.assertEqual(len(level.entities), 6)
            records = br.actor_records(level)
            self.assertEqual(len(records), 96)
            self.assertTrue(all(records[i * 16 + 4] != br.SENTINEL_DEAD for i in range(6)))
            path.write_text(json.dumps(dict(source, entities=source["entities"][:3] + extra + extra[:1])))
            with self.assertRaises(ValueError):
                levels.compile_level(path)

    def test_six_live_actors_render_within_the_object_budget(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        for y in range(16):
            for x in range(16):
                set_test_world_byte(cgb, br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
        for address, value in ((br.PLAYER_XL, 0x80), (br.PLAYER_XH, 2), (br.PLAYER_YL, 0x80), (br.PLAYER_YH, 8),
                               (br.ANGLE, 0), (br.ACTOR_COUNT, 6)):
            set_test_world_byte(cgb, address, value)
        # Six chasers fanned out ahead: the draw pass visits every slot, admits
        # what the budget allows and degrades or refuses the rest.
        for slot in range(6):
            x, y = 4 * 256 + slot * 160, 8 * 256 + (slot - 2) * 96
            for offset, value in enumerate((x & 255, x >> 8, y & 255, y >> 8, br.SENTINEL_CHASE, 3)):
                set_test_world_byte(cgb, br.ENTITY_SLOTS + slot * 16 + offset, value)
            set_test_world_byte(cgb, br.ENTITY_SLOTS + slot * 16 + br.ACTOR_KIND_OFFSET, slot % 3)
        set_test_world_byte(cgb, br.SENTINEL_STATE, br.SENTINEL_CHASE)
        for _ in range(3):
            cgb.run(until_presentations=cgb.presentations + 1, max_steps=6_000_000)
        budget = oam_budget(cgb)
        self.assertLessEqual(budget["max_oam_per_scanline"], 10)
        self.assertLessEqual(budget["visible_oam"], 40)
        self.assertEqual(cgb.read8(br.ACTOR_COUNT), 6)
        self.assertTrue(all(cgb.read8(br.ENTITY_SLOTS + slot * 16 + 4) != br.SENTINEL_DEAD for slot in range(6)))
        if br.SLIM_DISPLAY:
            # The skull counts all six living hostiles.
            cgb.call_subroutine("prepare_hud_tiles", max_steps=500_000)
            self.assertEqual(cgb.read8(br.HUD_PACKET + 4), br.HUD_SMALL_DIGIT_BASE + 6)


if __name__ == "__main__":
    unittest.main()
