"""Full-screen presentation modes: composition, the title gate and continues."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4 import screens  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402


class ScreenCompositionTests(unittest.TestCase):
    def test_every_screen_fits_the_idle_composition_window(self):
        for name, patterns, tilemap, _ in screens.screen_assets():
            count = len(patterns) // 16
            self.assertLessEqual(count, screens.SCREEN_PATTERN_CAPACITY, name)
            self.assertEqual(len(patterns) % 16, 0, name)
            self.assertEqual(len(tilemap), screens.SCREEN_MAP_BYTES, name)
            self.assertLess(max(tilemap), count, f"{name} maps a pattern it does not carry")

    def test_digits_are_the_first_patterns_so_a_map_write_shows_a_number(self):
        for name, patterns, _, _ in screens.screen_assets():
            self.assertGreaterEqual(len(patterns) // 16, screens.DIGIT_PATTERNS, name)
        reference = screens.compose_screen(())[0][:screens.DIGIT_PATTERNS * 16]
        for name, patterns, _, _ in screens.screen_assets():
            self.assertEqual(patterns[:screens.DIGIT_PATTERNS * 16], reference, name)

    def test_composition_is_deterministic_and_fits_one_bank(self):
        self.assertEqual(screens.screen_directory(), screens.screen_directory())
        self.assertLessEqual(len(screens.screen_directory()), 0x4000)

    def test_screens_reserve_the_runtime_slots_they_need(self):
        slots = {name: offsets for name, _, _, offsets in screens.screen_assets()}
        self.assertEqual(len(slots["title"]), 1)             # the skill digit
        self.assertEqual(len(slots["intermission"]), br.PASSWORD_DIGITS)
        self.assertEqual(len(slots["password"]), br.PASSWORD_DIGITS)
        for name, offsets in slots.items():
            self.assertLessEqual(len(offsets), br.SCREEN_SLOT_CAPACITY, name)
            self.assertEqual(len(set(offsets)), len(offsets), name)
            for offset in offsets:
                self.assertLess(offset, screens.SCREEN_MAP_BYTES, name)
        # The code's four cells are adjacent, so it reads as one number.
        for name in ("intermission", "password"):
            self.assertEqual(list(slots[name]), list(range(slots[name][0], slots[name][0] + 4)), name)

    def test_a_blank_pattern_follows_the_digits_so_a_cell_can_be_cleared(self):
        for name, patterns, tilemap, _ in screens.screen_assets():
            blank = patterns[screens.BLANK_PATTERN * 16:screens.BLANK_PATTERN * 16 + 16]
            self.assertEqual(blank, bytes(16), name)

    def test_every_continue_code_is_distinct_and_typeable(self):
        codes = screens.continue_codes(br.LEVEL_COUNT, br.DIFFICULTY_LEVELS)
        self.assertEqual(len(codes), br.LEVEL_COUNT * br.DIFFICULTY_LEVELS)
        self.assertEqual(len(set(codes)), len(codes))
        for code in codes:
            self.assertEqual(len(code), br.PASSWORD_DIGITS)
            self.assertTrue(all(0 <= digit <= 9 for digit in code))
            self.assertNotEqual(code[0], 0)      # reads back exactly as shown
        self.assertEqual(codes, screens.continue_codes(br.LEVEL_COUNT, br.DIFFICULTY_LEVELS))


class TitleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def test_title_holds_the_world_until_start(self):
        cgb = CGB(self.rom, self.asm.labels)
        cgb.button_provider = lambda *_: 0
        world = self.asm.labels["main_loop"]
        for _ in range(4_000_000):
            if cgb.pc == world:
                break
            cgb.step()
        self.assertNotEqual(cgb.pc, world, "the world started without START")
        # A full-screen mode owns the whole background: LCD and BG on, no
        # objects, and VBlank only so the HUD's STAT split cannot fire.
        self.assertEqual(cgb.io[0x40], 0x81)
        self.assertEqual(cgb.read8(0xFFFF), 1)
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)

    def test_the_title_never_overflows_the_simulation_queue(self):
        cgb = CGB(self.rom, self.asm.labels)
        cgb.button_provider = lambda *_: 0
        # Well past the 63-slot ring at one packet per VBlank.
        for _ in range(6_000_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.INPUT_QUEUE_OVERFLOW), 0)
        self.assertEqual(cgb.read8(br.INPUT_QUEUE_HEAD), cgb.read8(br.INPUT_QUEUE_TAIL))

    def test_start_enters_the_world_with_its_own_interrupt_and_lcd_state(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self.assertEqual(cgb.pc, self.asm.labels["main_loop"])
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_PLAYING)
        self.assertEqual(cgb.io[0x40], br.BG_LCDC)
        self.assertEqual(cgb.read8(0xFFFF), 3 if br.HUD_UNSIGNED else 1)
        # The harness released START, so the next press is still a rising edge.
        self.assertEqual(cgb.read8(self.asm.labels["input_last_raw"]), 0)


class ContinueCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()
        cls.codes = screens.continue_codes(br.LEVEL_COUNT, br.DIFFICULTY_LEVELS)

    @staticmethod
    def _press(cgb, button, frames=160_000):
        # Selection follows rising edges, so each press is a release too.
        for held in (button, 0):
            cgb.button_provider = lambda *_, value=held: value
            for _ in range(frames):
                cgb.step()

    def _title(self):
        cgb = CGB(self.rom, self.asm.labels)
        cgb.button_provider = lambda *_: 0
        for _ in range(900_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)
        return cgb

    def _type(self, cgb, code):
        self._press(cgb, 0x40)                 # SELECT opens code entry
        self.assertEqual(cgb.read8(br.SCREEN_INDEX), br.SCREEN_PASSWORD)
        for index, digit in enumerate(code):
            for _ in range(digit):
                self._press(cgb, 0x04)         # up rolls the digit
            if index < len(code) - 1:
                self._press(cgb, 0x01)         # right moves the cursor
        self.assertEqual([cgb.read8(br.SCREEN_DIGITS + i) for i in range(br.PASSWORD_DIGITS)],
                         list(code))

    def test_a_code_starts_the_campaign_at_the_sector_and_skill_it_names(self):
        level, skill = br.LEVEL_COUNT - 1, br.DIFFICULTY_LEVELS - 1
        cgb = self._title()
        self._type(cgb, self.codes[level * br.DIFFICULTY_LEVELS + skill])
        self._press(cgb, 0x80)                 # START accepts
        cgb.button_provider = lambda *_: 0
        for _ in range(900_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.LEVEL_INDEX), level)
        self.assertEqual(cgb.read8(br.DIFFICULTY), skill)
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_PLAYING)
        self.assertEqual(cgb.read8(br.LEVEL_BANK), br.LEVEL_ROM_BANK_BASE + level)
        self.assertEqual(bytes(cgb.wramx[2][br.MAP - 0xD000:br.MAP - 0xD000 + 256]),
                         br.CAMPAIGN[level].grid)

    def test_an_unknown_code_is_refused_and_select_cancels(self):
        cgb = self._title()
        before = cgb.read8(br.DIFFICULTY)
        self._type(cgb, (9, 9, 9, 9))          # not in the table
        self._press(cgb, 0x80)
        self.assertEqual(cgb.read8(br.SCREEN_INDEX), br.SCREEN_PASSWORD, "a bad code was taken")
        self.assertEqual(cgb.read8(br.LEVEL_INDEX), 0)
        self._press(cgb, 0x40)                 # SELECT cancels back to the title
        for _ in range(300_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.SCREEN_INDEX), br.SCREEN_TITLE)
        self.assertEqual(cgb.read8(br.DIFFICULTY), before)
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)

    def test_the_intermission_shows_the_code_for_where_the_player_reached(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.button_provider = lambda *_: 0
        cgb.wramx[2][br.LEVEL_COMPLETE - 0xD000] = 1
        for _ in range(60_000_000):
            if cgb.read8(br.GAME_MODE) == br.MODE_INTERMISSION and cgb.io[0x40] == 0x81:
                break
            cgb.step()
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_INTERMISSION)
        level, skill = cgb.read8(br.LEVEL_INDEX), cgb.read8(br.DIFFICULTY)
        self.assertEqual([cgb.read8(br.SCREEN_DIGITS + i) for i in range(br.PASSWORD_DIGITS)],
                         list(self.codes[level * br.DIFFICULTY_LEVELS + skill]))


class ModeMachineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _advance(self, cgb, predicate, limit=60_000_000):
        for _ in range(limit):
            if predicate():
                return True
            cgb.step()
        return False

    def _cycle(self, address, value, expected_mode, cgb=None, expected_level=0):
        cgb = cgb or run_to_world(CGB(self.rom, self.asm.labels))
        cgb.button_provider = lambda *_: 0
        cgb.wramx[2][address - 0xD000] = value
        # The world holds its last frame, then hands over to a results screen.
        self.assertTrue(self._advance(cgb, lambda: cgb.read8(br.GAME_MODE) != br.MODE_PLAYING),
                        "the world never left MODE_PLAYING")
        self.assertEqual(cgb.read8(br.GAME_MODE), expected_mode)
        self.assertTrue(self._advance(cgb, lambda: cgb.io[0x40] == 0x81), "no screen appeared")
        self.assertEqual(cgb.read8(0xFFFF), 1)
        # START loads the selected level and returns to the world.
        cgb.button_provider = lambda *_: 0x80
        world = self.asm.labels["main_loop"]
        self.assertTrue(self._advance(
            cgb, lambda: cgb.read8(br.GAME_MODE) == br.MODE_PLAYING and cgb.pc == world),
            "START did not restore the world")
        self.assertEqual(cgb.io[0x40], br.BG_LCDC)
        self.assertEqual(cgb.read8(br.LEVEL_INDEX), expected_level)
        self.assertEqual(cgb.read8(br.LEVEL_BANK), br.LEVEL_ROM_BANK_BASE + expected_level)
        self.assertEqual(bytes(cgb.wramx[2][br.MAP - 0xD000:br.MAP - 0xD000 + 256]),
                         br.CAMPAIGN[expected_level].grid)
        self.assertEqual(cgb.wramx[2][br.PLAYER_HEALTH - 0xD000], 99)
        self.assertEqual(cgb.wramx[2][br.LEVEL_COMPLETE - 0xD000], 0)
        self.assertEqual(cgb.wramx[2][br.PICKUP_COLLECTED - 0xD000], 0)
        return cgb

    def test_death_retries_the_same_sector(self):
        self._cycle(br.PLAYER_HEALTH, 0, br.MODE_GAMEOVER)

    def test_completing_every_sector_ends_the_campaign_and_restarts_it(self):
        cgb = None
        for index in range(1, len(br.CAMPAIGN)):
            cgb = self._cycle(br.LEVEL_COMPLETE, 1, br.MODE_INTERMISSION, cgb, expected_level=index)
        # The last sector has no successor: the ending restarts from sector one.
        self._cycle(br.LEVEL_COMPLETE, 1, br.MODE_ENDING, cgb, expected_level=0)


if __name__ == "__main__":
    unittest.main()
