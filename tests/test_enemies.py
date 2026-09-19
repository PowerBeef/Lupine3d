"""Enemy kinds and the skill setting that scales what they do to you."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4.levels import ENTITY_KIND_IDS  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402

DAMAGE, COOLDOWN, STEP, PALETTE = range(4)


class EnemyKindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()
        start = cls.asm.labels["actor_kind_stats"]
        cls.stats = [cls.rom[start + index * 4:start + index * 4 + 4] for index in range(4)]

    def test_the_table_covers_every_kind_byte_and_stays_playable(self):
        # The kind byte is masked to two bits, so all four records must be
        # playable even though only the authored kinds are ever written.
        self.assertGreaterEqual(len(self.stats), len(ENTITY_KIND_IDS))
        for index, record in enumerate(self.stats):
            self.assertTrue(1 <= record[DAMAGE] <= 99, index)
            self.assertTrue(1 <= record[COOLDOWN] <= 64, index)
            self.assertTrue(1 <= record[STEP] <= 64, index)
            self.assertLess(record[PALETTE], 8, index)
        for spare in self.stats[len(ENTITY_KIND_IDS):]:
            self.assertEqual(spare, self.stats[ENTITY_KIND_IDS["sentinel"]])

    def test_kinds_are_told_apart_by_palette_and_by_what_they_do(self):
        sentinel = self.stats[ENTITY_KIND_IDS["sentinel"]]
        skirmisher = self.stats[ENTITY_KIND_IDS["skirmisher"]]
        self.assertNotEqual(sentinel[PALETTE], skirmisher[PALETTE])
        self.assertGreater(skirmisher[STEP], sentinel[STEP])      # quicker
        self.assertLess(skirmisher[DAMAGE], sentinel[DAMAGE])     # and lighter
        # Sharing one OBJ palette would make two kinds indistinguishable, and
        # only palette 7 was free: 0 weapon, 1 Sentinel, 2 pickup, 3 muzzle
        # and decor, 4 decor, 5 the weapon's lit corners, 6 the reticle.
        used = {record[PALETTE] for record in self.stats[:len(ENTITY_KIND_IDS)]}
        self.assertEqual(len(used), len(ENTITY_KIND_IDS))
        self.assertIn(7, used)

    def test_authored_kinds_reach_the_actor_slots_of_every_level(self):
        for index, level in enumerate(br.CAMPAIGN):
            records = br.actor_records(level)
            for slot, entity in enumerate(level.entities):
                self.assertEqual(records[slot * 16 + br.ACTOR_KIND_OFFSET],
                                 ENTITY_KIND_IDS[entity.kind], (level.name, slot))
            bank = (br.LEVEL_ROM_BANK_BASE + index) * 0x4000 + br.LEVEL_ACTOR_OFFSET - 0x4000
            self.assertEqual(self.rom[bank:bank + len(records)], records, level.name)
        # The campaign actually uses the variety it can express.
        kinds = {entity.kind for level in br.CAMPAIGN for entity in level.entities}
        self.assertEqual(kinds, set(ENTITY_KIND_IDS))

    def test_the_loaded_slot_carries_its_kind_through_save_and_load(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        live = br.ACTIVE_LEVEL.entities
        self.assertEqual(cgb.wramx[2][br.SENTINEL_KIND - 0xD000], ENTITY_KIND_IDS[live[0].kind])
        for slot, entity in enumerate(live):
            base = br.ENTITY_SLOTS + slot * 16 - 0xD000
            self.assertEqual(cgb.wramx[2][base + br.ACTOR_KIND_OFFSET],
                             ENTITY_KIND_IDS[entity.kind], slot)


class SkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _damage(self, cgb, skill, base):
        cgb.write8(br.DIFFICULTY, skill)
        cgb.b = base
        cgb.call_subroutine("scale_contact_damage", max_steps=10_000)
        return cgb.b

    def test_skill_scales_contact_damage_and_nothing_else(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        for base in (4, 8, 14):
            self.assertEqual(self._damage(cgb, 0, base), base // 2, base)
            self.assertEqual(self._damage(cgb, 1, base), base, base)
            self.assertEqual(self._damage(cgb, 2, base), base + base // 2, base)

    def test_the_title_selects_skill_and_clamps_at_both_ends(self):
        cgb = CGB(self.rom, self.asm.labels)
        cgb.button_provider = lambda *_: 0
        for _ in range(900_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)
        self.assertEqual(cgb.read8(br.DIFFICULTY), 1)
        self.assertEqual(cgb.read8(br.SCREEN_DIGIT), 2)   # shown one-based

        def press(button, times=1):
            # Selection follows rising edges, so holding the pad is one step.
            for _ in range(times):
                for held in (button, 0):
                    cgb.button_provider = lambda *_, value=held: value
                    for _ in range(300_000):
                        cgb.step()

        press(0x01, 3)                                    # right, past the ceiling
        self.assertEqual(cgb.read8(br.DIFFICULTY), br.DIFFICULTY_LEVELS - 1)
        self.assertEqual(cgb.read8(br.SCREEN_DIGIT), br.DIFFICULTY_LEVELS)
        press(0x02, 4)                                    # left, past the floor
        self.assertEqual(cgb.read8(br.DIFFICULTY), 0)
        self.assertEqual(cgb.read8(br.SCREEN_DIGIT), 1)
        # Still on the title: skill never starts the game by itself.
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)


if __name__ == "__main__":
    unittest.main()
