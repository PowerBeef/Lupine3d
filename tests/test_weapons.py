"""Four weapons in an eighty-pattern window, what the trade between them is, and
which of them a sector puts in the player's hands."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402

DAMAGE, COOLDOWN = range(2)


class WeaponTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()
        start = cls.asm.labels["weapon_stats"]
        size = br.WEAPON_STAT_BYTES
        cls.stats = [cls.rom[start + i * size:start + (i + 1) * size]
                     for i in range(br.WEAPON_COUNT)]

    def test_the_shotgun_is_exactly_what_it_always_was(self):
        self.assertEqual(self.stats[0][DAMAGE], 1)
        self.assertEqual(self.stats[0][COOLDOWN], 0)

    def test_the_second_weapon_pays_for_its_damage_with_time(self):
        shotgun, slug = self.stats[0], self.stats[1]
        self.assertGreater(slug[DAMAGE], shotgun[DAMAGE])
        self.assertGreater(slug[COOLDOWN], shotgun[COOLDOWN])
        # Two damage has to be able to kill something the campaign fields.
        self.assertLessEqual(slug[DAMAGE], min(e.health for l in br.CAMPAIGN for e in l.entities))

    def test_every_weapon_fills_the_same_pattern_window_exactly(self):
        sheets = [payload for _, payload in br.make_weapon_assets()]
        self.assertEqual(len(sheets), br.WEAPON_COUNT)
        for sheet in sheets:
            self.assertEqual(len(sheet), br.WEAPON_TILE_BYTES)
        self.assertEqual(br.WEAPON_PATTERNS, br.WEAPON_TILE_BYTES // 16)
        self.assertEqual(len(set(sheets)), br.WEAPON_COUNT, "every weapon must look different")
        first, second = br.make_weapon_tiles(), br.make_slug_tiles()
        # The sheets live in their own bank, in weapon order, and the source
        # table the swap reads points at each one.
        start = br.WEAPON_ROM_BANK * 0x4000
        for index, sheet in enumerate(sheets):
            offset = start + index * br.WEAPON_TILE_BYTES
            self.assertEqual(self.rom[offset:offset + br.WEAPON_TILE_BYTES], sheet, index)
            table = self.asm.labels["weapon_sources"] + index * 2
            self.assertEqual(self.rom[table] | self.rom[table + 1] << 8, 0x4000 + index * br.WEAPON_TILE_BYTES)
        # Streaming is the only option: the window is one weapon's cels, and
        # the rest of bank 1's OBJ space is spoken for.
        self.assertEqual(br.WEAPON_TILE_BASE * 16 + br.WEAPON_TILE_BYTES,
                         br.RETICLE_TILE * 16)

    def test_the_second_weapon_is_drawn_not_generated(self):
        # Every cel must carry ink, and no two consecutive cels may be equal,
        # or the animation would stall on a frame.
        size = br.WEAPON_CEL_PATTERNS * 16
        cels = [br.make_slug_tiles()[i * size:(i + 1) * size] for i in range(br.WEAPON_CELS)]
        for index, cel in enumerate(cels):
            self.assertNotEqual(cel, bytes(size), index)
        # The legacy art profile carries one cel per weapon and no animation.
        if len(cels) > 1:
            self.assertGreater(len(set(cels)), 1, "every cel is identical")
        self.assertEqual(br.make_slug_tiles(), br.make_slug_tiles(), "not deterministic")


class WeaponSwapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    @staticmethod
    def _window(cgb):
        base = br.WEAPON_TILE_BASE * 16
        return bytes(cgb.vram[1][base:base + br.WEAPON_TILE_BYTES])

    def _press(self, cgb, button, frames=120_000):
        for held in (button, 0):
            cgb.button_provider = lambda *_, value=held: value
            for _ in range(frames):
                cgb.step()

    def test_the_world_starts_with_the_shotgun_resident(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 0)
        self.assertEqual(self._window(cgb), br.make_weapon_tiles())

    def test_select_streams_the_other_weapon_into_the_same_patterns(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        tiles = [cgb.oam[entry * 4 + 2] for entry in range(16)]
        self._press(cgb, 0x40)
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 1)
        self.assertEqual(cgb.read8(br.WEAPON_RELOAD), 0, "the swap was never serviced")
        self.assertEqual(self._window(cgb), br.make_slug_tiles())
        # Only the pattern contents changed, so the weapon's sixteen objects
        # still name the same pattern IDs and no OAM rewrite was needed.
        self.assertEqual([cgb.oam[entry * 4 + 2] for entry in range(16)], tiles)
        self._press(cgb, 0x40)
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 0)
        self.assertEqual(self._window(cgb), br.make_weapon_tiles())

    def test_a_swap_never_starts_a_transfer_outside_vblank(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        before = getattr(cgb, "unsafe_gdma_starts", 0)
        for _ in range(3):
            self._press(cgb, 0x40)
        self.assertEqual(getattr(cgb, "unsafe_gdma_starts", 0), before)

    def test_the_weapon_in_hand_decides_what_a_hit_takes_off(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        for index in range(br.WEAPON_COUNT):
            cgb.write8(br.WEAPON_INDEX, index)
            cgb.call_subroutine("weapon_damage", max_steps=10_000)
            start = self.asm.labels["weapon_stats"] + index * br.WEAPON_STAT_BYTES
            self.assertEqual(cgb.a, self.rom[start + DAMAGE], index)

    def test_a_slower_weapon_cannot_fire_while_it_is_recovering(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self._press(cgb, 0x40)                       # to the slug rifle
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 1)
        cgb.write8(br.WEAPON_COOLDOWN, 0)
        self._press(cgb, 0x10, frames=20_000)        # one trigger pull
        recovery = cgb.read8(br.WEAPON_COOLDOWN)
        self.assertGreater(recovery, 0, "the slug rifle fired with no recovery at all")
        self.assertLessEqual(recovery, self.rom[self.asm.labels["weapon_stats"]
                                                + br.WEAPON_STAT_BYTES + COOLDOWN])

    def test_a_swap_keeps_the_recovery_the_last_shot_started(self):
        # Recovery belongs to the shot, not to the weapon in hand: a swap that
        # cleared it would let the slug rifle fire and swap away its cost.
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.write8(br.WEAPON_COOLDOWN, 5)
        cgb.call_subroutine("swap_weapon", max_steps=10_000)
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 1)
        self.assertEqual(cgb.read8(br.WEAPON_COOLDOWN), 5)

    def test_the_arsenal_follows_the_sector_and_select_skips_what_is_not_owned(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        # Sector 1 owns the first two weapons: SELECT cycles between them.
        self.assertEqual(cgb.read8(br.WEAPONS_OWNED), 0b0011)
        seen = []
        for _ in range(3):
            self._press(cgb, 0x40)
            seen.append(cgb.read8(br.WEAPON_INDEX))
        self.assertEqual(seen, [1, 0, 1])
        # With the whole arsenal owned SELECT walks all four, each streaming
        # its own sheet into the same window. WEAPONS_OWNED is a fixed-WRAM
        # campaign scalar, so the test may set it directly.
        cgb.write8(br.WEAPONS_OWNED, (1 << br.WEAPON_COUNT) - 1)
        sheets = [payload for _, payload in br.make_weapon_assets()]
        for expected in (2, 3, 0, 1):
            self._press(cgb, 0x40)
            self.assertEqual(cgb.read8(br.WEAPON_INDEX), expected)
            self.assertEqual(cgb.read8(br.WEAPON_RELOAD), 0, "the swap was never serviced")
            self.assertEqual(self._window(cgb), sheets[expected], expected)
        # Only the weapon in hand owned: SELECT gives up without a swap.
        cgb.write8(br.WEAPONS_OWNED, 1 << 1)
        self._press(cgb, 0x40)
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 1)
        self.assertEqual(cgb.read8(br.WEAPON_RELOAD), 0)

    def test_a_weapon_no_longer_owned_drops_to_the_first_on_load(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.write8(br.WEAPONS_OWNED, 0xFF)
        cgb.write8(br.WEAPON_INDEX, 3)
        cgb.rom_bank = 1
        cgb.call_subroutine("load_level", max_steps=4_000_000)
        # Sector 1 owns two weapons, so the arsenal is rebuilt from the sector
        # and the fourth weapon in hand is put down.
        self.assertEqual(cgb.read8(br.WEAPONS_OWNED), 0b0011)
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 0)
        self.assertEqual(br.WEAPON_UNLOCK_SECTORS, (0, 0, 6, 12))  # the showcase arsenal (game.json `weapons`)

    def test_the_weapon_stays_in_hand_across_a_level_load(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self._press(cgb, 0x40)
        # The press stops wherever its step count lands, which can be inside a
        # banked table lookup. load_level's real callers (the title and the
        # transition screens) always run it with ROM bank 1 mapped, so give
        # the direct call the same precondition.
        cgb.rom_bank = 1
        cgb.call_subroutine("load_level", max_steps=4_000_000)
        cgb.call_subroutine("init_vram", max_steps=4_000_000)
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 1)
        self.assertEqual(self._window(cgb), br.make_slug_tiles())


if __name__ == "__main__":
    unittest.main()
