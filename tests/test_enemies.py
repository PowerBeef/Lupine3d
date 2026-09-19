"""Enemy kinds and the skill setting that scales what they do to you."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4.levels import ENTITY_KIND_IDS  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402

DAMAGE, COOLDOWN, STEP, PALETTE, DROP = range(5)


class EnemyKindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()
        start = cls.asm.labels["actor_kind_stats"]
        size = br.ACTOR_KIND_RECORD_BYTES
        cls.stats = [cls.rom[start + index * size:start + (index + 1) * size] for index in range(4)]

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


class PatrolTests(unittest.TestCase):
    """A route, not a bob: heading, collision and waking."""

    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _world(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.io[br.SVBK & 0x7F] = 2        # the simulation's live world
        return cgb

    @staticmethod
    def _place(cgb, *, actor_x, actor_y, player_x, player_y):
        for address, value in ((br.SENTINEL_XL, actor_x & 0xFF), (br.SENTINEL_XH, actor_x >> 8),
                               (br.SENTINEL_YL, actor_y & 0xFF), (br.SENTINEL_YH, actor_y >> 8),
                               (br.PLAYER_XL, player_x & 0xFF), (br.PLAYER_XH, player_x >> 8),
                               (br.PLAYER_YL, player_y & 0xFF), (br.PLAYER_YH, player_y >> 8)):
            cgb.write8(address, value)

    def _cell(self, cgb, x, y):
        return cgb.read8(br.MAP + (y << 4) + x)

    def _empty_cell(self, cgb, avoid=()):
        for y in range(1, 15):
            for x in range(1, 15):
                if not self._cell(cgb, x, y) and (x, y) not in avoid:
                    if all(not self._cell(cgb, x + dx, y + dy)
                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                        return x, y
        self.fail("the level has no open cell with four open neighbours")

    def test_the_level_header_supplies_the_activation_radius_in_whole_cells(self):
        cgb = self._world()
        authored = br.ACTIVE_LEVEL.entities[0].activation_radius_q4
        self.assertEqual(cgb.read8(br.ACTIVATION_RADIUS), authored >> 4)
        self.assertGreater(authored >> 4, 0, "a radius that rounds to zero never wakes anything")

    def test_a_dormant_actor_waits_until_the_player_is_inside_that_radius(self):
        cgb = self._world()
        radius = cgb.read8(br.ACTIVATION_RADIUS)
        x, y = self._empty_cell(cgb)
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_DORMANT)
        # Far away on one axis only: the radius gates both.
        self._place(cgb, actor_x=(x << 8) | 0x80, actor_y=(y << 8) | 0x80,
                    player_x=((x + radius) << 8) | 0x80, player_y=(y << 8) | 0x80)
        for _ in range(8):
            cgb.call_subroutine("sentinel_ai_tick", max_steps=400_000)
        self.assertEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_DORMANT)
        self._place(cgb, actor_x=(x << 8) | 0x80, actor_y=(y << 8) | 0x80,
                    player_x=((x + radius - 1) << 8) | 0x80, player_y=(y << 8) | 0x80)
        cgb.call_subroutine("sentinel_ai_tick", max_steps=400_000)
        self.assertNotEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_DORMANT)

    def test_every_slot_starts_on_its_own_compass_point(self):
        cgb = self._world()
        headings = [cgb.read8(br.ACTOR_PATROL + slot) for slot in range(br.MAX_ACTORS)]
        self.assertEqual(headings, list(range(br.MAX_ACTORS)))

    def test_patrol_walks_its_heading_and_stays_out_of_walls(self):
        cgb = self._world()
        x, y = self._empty_cell(cgb)
        moved = {}
        for heading, (dx, dy) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
            self._place(cgb, actor_x=(x << 8) | 0x80, actor_y=(y << 8) | 0x80,
                        player_x=0x0080, player_y=0x0080)
            cgb.write8(br.SENTINEL_STATE, br.SENTINEL_PATROL)
            cgb.write8(br.ACTOR_PATROL, heading)
            cgb.call_subroutine("sentinel_patrol_step", max_steps=100_000)
            after_x = cgb.read8(br.SENTINEL_XL) | cgb.read8(br.SENTINEL_XH) << 8
            after_y = cgb.read8(br.SENTINEL_YL) | cgb.read8(br.SENTINEL_YH) << 8
            step = cgb.read8(br.ACTOR_STEP)
            self.assertEqual(after_x - ((x << 8) | 0x80), dx * step, heading)
            self.assertEqual(after_y - ((y << 8) | 0x80), dy * step, heading)
            self.assertEqual(self._cell(cgb, after_x >> 8, after_y >> 8), 0, heading)
            self.assertEqual(cgb.read8(br.ACTOR_PATROL), heading, "an accepted step keeps its heading")
            moved[heading] = (after_x, after_y)
        self.assertEqual(len(set(moved.values())), 4, "the four headings must go four ways")

    def test_a_refused_step_turns_the_actor_instead_of_moving_it(self):
        cgb = self._world()
        # Find an open cell with a wall to its east and aim the actor at it.
        for y in range(1, 15):
            for x in range(1, 15):
                if not self._cell(cgb, x, y) and self._cell(cgb, x + 1, y):
                    break
            else:
                continue
            break
        else:
            self.fail("the level has no open cell with a wall to its east")
        # Stand hard against the wall, so any step at all crosses into it.
        self._place(cgb, actor_x=(x << 8) | 0xFF, actor_y=(y << 8) | 0x80,
                    player_x=0x0080, player_y=0x0080)
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_PATROL)
        cgb.write8(br.ACTOR_PATROL, 0)                     # heading +x, into the wall
        cgb.call_subroutine("sentinel_patrol_step", max_steps=100_000)
        self.assertEqual(cgb.read8(br.SENTINEL_XL), 0xFF, "a refused step must not move the actor")
        self.assertEqual(cgb.read8(br.SENTINEL_XH), x)
        self.assertEqual(cgb.read8(br.ACTOR_PATROL), 1, "a refused step turns a quarter turn")

    def test_patrol_leaves_the_other_slots_headings_alone(self):
        cgb = self._world()
        x, y = self._empty_cell(cgb)
        for slot in range(br.MAX_ACTORS):
            cgb.write8(br.ACTOR_PATROL + slot, 2)
        cgb.write8(br.ENTITY_SLOT, 2)
        self._place(cgb, actor_x=(x << 8) | 0x80, actor_y=(y << 8) | 0x80,
                    player_x=0x0080, player_y=0x0080)
        cgb.write8(br.ACTOR_PATROL + 2, 0)
        cgb.call_subroutine("sentinel_patrol_step", max_steps=100_000)
        self.assertEqual([cgb.read8(br.ACTOR_PATROL + slot) for slot in range(br.MAX_ACTORS)],
                         [2, 2, 0, 2])
