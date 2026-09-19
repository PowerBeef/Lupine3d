"""Full-screen presentation modes: composition budget and the title gate."""
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

    def test_the_intermission_reserves_a_runtime_digit_slot(self):
        slots = {name: offsets for name, _, _, offsets in screens.screen_assets()}
        self.assertEqual(len(slots["intermission"]), 1)
        self.assertLess(slots["intermission"][0], screens.SCREEN_MAP_BYTES)


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


if __name__ == "__main__":
    unittest.main()
