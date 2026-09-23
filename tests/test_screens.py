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
        self.assertEqual(len(slots["password"]), br.PASSWORD_DIGITS)
        # The intermission carries the code and then what the sector cost:
        # two digits of kills and three of seconds.
        self.assertEqual(len(slots["intermission"]), br.PASSWORD_DIGITS + 2 + 3)
        # The ending has no code to show, only the run: three digits of kills
        # and four of seconds.
        self.assertEqual(len(slots["ending"]), 3 + 4)
        for name, offsets in slots.items():
            self.assertLessEqual(len(offsets), br.SCREEN_SLOT_CAPACITY, name)
            self.assertEqual(len(set(offsets)), len(offsets), name)
            for offset in offsets:
                self.assertLess(offset, screens.SCREEN_MAP_BYTES, name)
        # The code's four cells are adjacent, so it reads as one number, and so
        # is every run of digits a screen writes.
        for name, runs in (("intermission", (4, 2, 3)), ("password", (4,)), ("ending", (3, 4))):
            offsets, start = list(slots[name]), 0
            for length in runs:
                run = offsets[start:start + length]
                self.assertEqual(run, list(range(run[0], run[0] + length)), (name, start))
                start += length
            self.assertEqual(start, len(offsets), name)

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

    def test_screen_state_borrows_the_map_buffer_and_enter_world_takes_it_back(self):
        # Screen slots live in the bottom of the BG map staging buffer: a
        # full-screen mode owns the whole background, so composition is idle
        # for exactly as long as that state exists.
        self.assertEqual(br.SCREEN_STATE, br.VIEW_MAP)
        self.assertLessEqual(br.SCREEN_STATE_END, br.VIEW_MAP + br.VIEW_MAP_BYTES)
        cgb = CGB(self.rom, self.asm.labels)
        cgb.button_provider = lambda *_: 0
        for _ in range(900_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)
        # The title reserves one slot, and writing its digit marks the buffer.
        self.assertEqual(cgb.read8(br.SCREEN_SLOT_COUNT), 1)
        self.assertEqual(cgb.read8(br.SCREEN_DIGIT), cgb.read8(br.DIFFICULTY) + 1)
        # enter_world repeats init_vram, whose loop refills every byte of it,
        # so a screen never has to put anything back.
        cgb = run_to_world(cgb)
        for offset in range(br.SCREEN_STATE_END - br.SCREEN_STATE):
            self.assertEqual(cgb.read8(br.SCREEN_STATE + offset), br.CEILING_TILE, hex(offset))


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
        self.assertEqual((cgb.read8(br.LEVEL_BANK), cgb.read8(br.LEVEL_PAGE)), br.level_location(level))
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
        # START loads the selected level and returns to the world. Pressed
        # as rising edges, not held: an intermission that crosses into the
        # next episode shows that episode's closing and opening screens on
        # the way, and each of them waits for a START of its own.
        counter = {"n": 0}
        def start_edges(*_):
            counter["n"] += 1
            return 0x80 if (counter["n"] // 4) % 2 else 0
        cgb.button_provider = start_edges
        world = self.asm.labels["main_loop"]
        self.assertTrue(self._advance(
            cgb, lambda: cgb.read8(br.GAME_MODE) == br.MODE_PLAYING and cgb.pc == world),
            "START did not restore the world")
        self.assertEqual(cgb.io[0x40], br.BG_LCDC)
        self.assertEqual(cgb.read8(br.LEVEL_INDEX), expected_level)
        self.assertEqual((cgb.read8(br.LEVEL_BANK), cgb.read8(br.LEVEL_PAGE)), br.level_location(expected_level))
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


class SlotAddressTests(unittest.TestCase):
    """Where a reserved digit actually lands on the background map.

    Checking the digit in WRAM is not enough: every slot on row eight or
    beyond used to be written eight rows too high, because the row offset
    passed 255 and the carry was dropped. The continue code sat on row nine,
    so it was written where nobody could read it.
    """

    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def test_every_reserved_slot_addresses_the_cell_it_reserved(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        for index, (name, _, _, offsets) in enumerate(screens.screen_assets()):
            for slot, offset in enumerate(offsets):
                cgb.write8(br.SCREEN_SLOTS + slot * 2, offset & 0xFF)
                cgb.write8(br.SCREEN_SLOTS + slot * 2 + 1, offset >> 8)
            for slot, offset in enumerate(offsets):
                row, column = divmod(offset, screens.SCREEN_COLUMNS)
                cgb.c = slot
                cgb.call_subroutine("screen_slot_address", max_steps=10_000)
                self.assertEqual(cgb.hl, 0x9800 + row * 32 + column,
                                 f"{name} slot {slot} at row {row}, column {column}")

    def test_an_unused_slot_is_left_alone(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.write8(br.SCREEN_SLOTS, 0xFF); cgb.write8(br.SCREEN_SLOTS + 1, 0xFF)
        cgb.c = 0
        cgb.call_subroutine("screen_slot_address", max_steps=10_000)
        self.assertFalse(0x9800 <= cgb.hl < 0xA000, "an unused slot must not address a map cell")
        self.assertEqual(cgb.d, 0xFF, "the caller tells an unused slot by D")


class ResultsStatisticsTests(unittest.TestCase):
    """What a results screen reports, and how a number becomes digits."""

    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _world(self):
        return run_to_world(CGB(self.rom, self.asm.labels))

    def _digits(self, cgb, first, count):
        return [cgb.read8(br.SCREEN_DIGITS + first + i) for i in range(count)]

    def _write_number(self, cgb, value, digits, slot=0):
        cgb.write8(br.SCREEN_VALUE, value & 0xFF)
        cgb.write8(br.SCREEN_VALUE + 1, value >> 8)
        cgb.b, cgb.c = digits, slot
        cgb.call_subroutine("screen_write_number", max_steps=2_000_000)
        return self._digits(cgb, slot, digits)

    def test_a_number_becomes_the_digits_a_screen_writes(self):
        cgb = self._world()
        for value, digits in ((0, 2), (7, 2), (99, 2), (0, 3), (5, 3), (137, 3),
                              (999, 3), (1234, 4), (9999, 4)):
            self.assertEqual(self._write_number(cgb, value, digits),
                             [int(d) for d in str(value).rjust(digits, "0")],
                             (value, digits))

    def test_a_number_too_wide_for_its_field_keeps_its_low_digits(self):
        # Three digits cannot show 1234; what it must not do is run past its
        # slots into the next field.
        cgb = self._world()
        self.assertEqual(len(self._write_number(cgb, 1234, 3)), 3)
        self.assertEqual(cgb.read8(br.SCREEN_SLOT_INDEX), 3)

    def test_vblanks_become_whole_seconds(self):
        cgb = self._world()
        for vblanks in (0, 59, 60, 61, 599, 3600, 59_940):
            cgb.write8(br.SCREEN_VALUE, vblanks & 0xFF)
            cgb.write8(br.SCREEN_VALUE + 1, vblanks >> 8)
            cgb.call_subroutine("screen_value_seconds", max_steps=4_000_000)
            seconds = cgb.read8(br.SCREEN_VALUE) | cgb.read8(br.SCREEN_VALUE + 1) << 8
            self.assertEqual(seconds, vblanks // br.VBLANKS_PER_SECOND, vblanks)

    def test_the_intermission_reports_the_sector_just_cleared(self):
        cgb = self._world()
        cgb.io[br.SVBK & 0x7F] = 2
        cgb.write8(br.SECTOR_KILLS, 3)
        cgb.write8(br.SECTOR_TIME, 4_500 & 0xFF)      # 75 seconds
        cgb.write8(br.SECTOR_TIME + 1, 4_500 >> 8)
        cgb.call_subroutine("screen_sector_stats", max_steps=4_000_000)
        self.assertEqual(self._digits(cgb, br.PASSWORD_DIGITS, 2), [0, 3])
        self.assertEqual(self._digits(cgb, br.PASSWORD_DIGITS + 2, 3), [0, 7, 5])
        # The code's own four digits are written separately and untouched here.
        self.assertEqual(cgb.read8(br.SCREEN_SLOT_INDEX), br.PASSWORD_DIGITS + 5)

    def test_the_ending_reports_the_whole_run(self):
        cgb = self._world()
        cgb.io[br.SVBK & 0x7F] = 2
        cgb.write8(br.CAMPAIGN_KILLS, 14)
        cgb.write8(br.CAMPAIGN_TIME, 36_000 & 0xFF)   # ten minutes
        cgb.write8(br.CAMPAIGN_TIME + 1, 36_000 >> 8)
        cgb.call_subroutine("screen_campaign_stats", max_steps=8_000_000)
        self.assertEqual(self._digits(cgb, 0, 3), [0, 1, 4])
        self.assertEqual(self._digits(cgb, 3, 4), [0, 6, 0, 0])

    def test_a_sector_starts_with_no_kills_and_its_own_clock(self):
        cgb = self._world()
        cgb.io[br.SVBK & 0x7F] = 2
        cgb.write8(br.SECTOR_KILLS, 9)
        # The previous sector's clock ran on. load_level used to take it as the
        # new sector's start, and init_simulation then reset the clock under
        # it, so the first sector time after a load was measured from the
        # wrong origin. Every load reaches init_simulation (enter_world), which
        # arms the baseline from the clock it has just reset.
        cgb.write8(br.SIM_CLOCK, 0x34); cgb.write8(br.SIM_CLOCK + 1, 0x12)
        cgb.call_subroutine("load_level", max_steps=4_000_000)
        self.assertEqual(cgb.read8(br.SECTOR_KILLS), 0)
        cgb.call_subroutine("init_simulation", max_steps=4_000_000)
        live = cgb.wramx[2]
        start = live[br.SECTOR_START - 0xD000] | live[br.SECTOR_START + 1 - 0xD000] << 8
        clock = cgb.read8(br.SIM_CLOCK) | cgb.read8(br.SIM_CLOCK + 1) << 8
        # The clock restarts from zero; a VBlank may tick it during the call.
        self.assertLessEqual(start, clock)
        self.assertLess(clock, 16)

    def test_clearing_a_sector_folds_it_into_the_run(self):
        cgb = self._world()
        cgb.io[br.SVBK & 0x7F] = 2
        cgb.write8(br.CAMPAIGN_KILLS, 5)
        cgb.write8(br.CAMPAIGN_TIME, 1_000 & 0xFF); cgb.write8(br.CAMPAIGN_TIME + 1, 1_000 >> 8)
        cgb.write8(br.SECTOR_KILLS, 4)
        clock = cgb.read8(br.SIM_CLOCK) | cgb.read8(br.SIM_CLOCK + 1) << 8
        start = (clock - 750) & 0xFFFF
        cgb.write8(br.SECTOR_START, start & 0xFF); cgb.write8(br.SECTOR_START + 1, start >> 8)
        cgb.call_subroutine("stamp_sector_result", max_steps=100_000)
        self.assertEqual(cgb.read8(br.SECTOR_TIME) | cgb.read8(br.SECTOR_TIME + 1) << 8, 750)
        self.assertEqual(cgb.read8(br.CAMPAIGN_TIME) | cgb.read8(br.CAMPAIGN_TIME + 1) << 8, 1_750)
        self.assertEqual(cgb.read8(br.CAMPAIGN_KILLS), 9)


class EpisodeScreenTests(unittest.TestCase):
    """The title opens episode one; later episodes open on their first sector
    and close on the intermission that crossed into the next."""
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _start_every(self, cgb, samples):
        """START held for `samples` joypad samples (one per VBlank), then
        released for as many: a rising edge every other period."""
        counter = {"n": 0}
        def provider(*_):
            counter["n"] += 1
            return 0x80 if (counter["n"] // samples) % 2 else 0
        cgb.button_provider = provider

    def _call(self, cgb, routine):
        self._start_every(cgb, 4)
        cgb.call_subroutine(routine, max_steps=3_000_000)

    def test_the_screens_exist_in_order_and_fit_the_bank(self):
        from lupine3d_v4.screens import SCREEN_EPISODE_CLOSINGS, SCREEN_EPISODE_OPENINGS, SCREEN_SOURCES
        self.assertEqual(len(SCREEN_EPISODE_CLOSINGS), len(br.EPISODE_STARTS))
        self.assertEqual(len(SCREEN_EPISODE_OPENINGS), len(br.EPISODE_STARTS))
        for index in SCREEN_EPISODE_CLOSINGS + SCREEN_EPISODE_OPENINGS:
            self.assertLess(index, len(SCREEN_SOURCES))
        self.assertEqual(br.EPISODE_STARTS, tuple(br.EPISODE_SECTORS * n for n in range(1, len(br.EPISODE_STARTS) + 1)))

    def test_no_episode_screen_shows_inside_an_episode(self):
        from lupine3d_v4.screens import SCREEN_EPISODE_CLOSINGS, SCREEN_EPISODE_OPENINGS
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        for index in (0, 3, br.EPISODE_STARTS[0] - 1, br.EPISODE_STARTS[0] + 1):
            cgb.write8(br.LEVEL_INDEX, index)
            cgb.write8(br.GAME_MODE, br.MODE_INTERMISSION)
            before = cgb.read8(br.SCREEN_INDEX)
            cgb.button_provider = lambda *_: 0
            cgb.call_subroutine("show_episode_closing", max_steps=20_000)
            cgb.call_subroutine("show_episode_opening", max_steps=20_000)
            self.assertEqual(cgb.read8(br.SCREEN_INDEX), before, index)
            self.assertNotIn(cgb.read8(br.SCREEN_INDEX), SCREEN_EPISODE_CLOSINGS + SCREEN_EPISODE_OPENINGS)

    def test_an_episode_start_opens_it_and_an_intermission_onto_it_closes_the_last(self):
        from lupine3d_v4.screens import SCREEN_EPISODE_CLOSINGS, SCREEN_EPISODE_OPENINGS
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        for episode, start in enumerate(br.EPISODE_STARTS):
            cgb.write8(br.LEVEL_INDEX, start)
            # A continue code into the episode: the opening alone.
            cgb.write8(br.GAME_MODE, br.MODE_TITLE)
            self._call(cgb, "show_episode_opening")
            self.assertEqual(cgb.read8(br.SCREEN_INDEX), SCREEN_EPISODE_OPENINGS[episode], episode)
            # The intermission that advanced onto it: the closing, then the
            # opening, each waiting for its own START.
            cgb.write8(br.GAME_MODE, br.MODE_INTERMISSION)
            shown = []
            original = cgb.write8
            def spy(address, value, original=original):
                if address == br.SCREEN_INDEX:
                    shown.append(value)
                original(address, value)
            cgb.write8 = spy
            self._call(cgb, "show_episode_closing")
            cgb.write8 = original
            self.assertEqual(shown, [SCREEN_EPISODE_CLOSINGS[episode], SCREEN_EPISODE_OPENINGS[episode]], episode)
            # A death retry onto the same index shows nothing.
            cgb.write8(br.GAME_MODE, br.MODE_GAMEOVER)
            cgb.button_provider = lambda *_: 0
            cgb.call_subroutine("show_episode_closing", max_steps=20_000)
            self.assertEqual(cgb.read8(br.SCREEN_INDEX), SCREEN_EPISODE_OPENINGS[episode])
