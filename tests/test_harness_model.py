"""The host harness's coarse PPU mode model, its mode-3 write counters, and the
conformance micro-program generator that keeps the CPU model honest."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from sm83 import Assembler  # noqa: E402
from sm83emu import CGB, LCDC, STAT, LY  # noqa: E402
import harness_conformance  # noqa: E402


def micro_rom(build) -> tuple[bytes, dict[str, int]]:
    """A 32 KiB ROM-only image whose program `build` emits at $0150."""
    a = Assembler(origin=0x0150)
    build(a)
    code = a.resolve()
    rom = bytearray([0xFF] * 0x8000)
    rom[0x0100:0x0104] = bytes((0x00, 0xC3, 0x50, 0x01))
    rom[0x0150:0x0150 + len(code)] = code
    return bytes(rom), dict(a.labels)


class PpuModeModelTests(unittest.TestCase):
    def test_modes_follow_the_line_and_grow_with_objects(self):
        cgb = CGB(bytes([0xFF] * 0x8000))
        cgb.io[LCDC & 0x7F] = 0x91
        cgb.ly, cgb.ppu_dots = 10, 0
        self.assertEqual(cgb.ppu_mode(), 2)
        cgb.ppu_dots = 79; self.assertEqual(cgb.ppu_mode(), 2)
        cgb.ppu_dots = 80; self.assertEqual(cgb.ppu_mode(), 3)
        cgb.ppu_dots = 251; self.assertEqual(cgb.ppu_mode(), 3)
        cgb.ppu_dots = 252; self.assertEqual(cgb.ppu_mode(), 0)
        # Three 8x16 objects on the line lengthen drawing by at least 18 dots.
        for index in range(3):
            cgb.oam[index * 4] = 10 + 16  # Y covers lines 10..25
        cgb.ppu_dots = 252; self.assertEqual(cgb.ppu_mode(), 3)
        cgb.ppu_dots = 252 + 18; self.assertEqual(cgb.ppu_mode(), 0)
        cgb.ly = 144; self.assertEqual(cgb.ppu_mode(), 1)
        cgb.io[LCDC & 0x7F] = 0x11; cgb.ly = 10; cgb.ppu_dots = 100
        self.assertEqual(cgb.ppu_mode(), 0, "an LCD that is off has no drawing mode")

    def test_stat_reads_carry_the_mode_and_coincidence_bits(self):
        cgb = CGB(bytes([0xFF] * 0x8000))
        cgb.io[LCDC & 0x7F] = 0x91
        cgb.io[STAT & 0x7F] = 0x40
        cgb.io[0x45] = 20
        cgb.ly, cgb.ppu_dots = 20, 100
        self.assertEqual(cgb.read8(STAT), 0x80 | 0x40 | 0x04 | 3)
        cgb.ly = 21
        self.assertEqual(cgb.read8(STAT), 0x80 | 0x40 | 3)

    def test_a_vram_write_while_drawing_is_counted_and_one_in_hblank_is_not(self):
        def program(a):
            # Wait for the start of line 10, spend about 180 dots in it, then
            # write VRAM while the PPU is still drawing; later write again from
            # VBlank, which is allowed.
            a.label("wait"); a.ldh_a_n(LY & 0xFF); a.cp_n(10); a.jr("wait", "nz")
            a.ld_r_n("b", 8); a.label("delay"); a.dec_r("b"); a.jr("delay", "nz")
            a.ld_r_n("a", 1); a.ld_abs_a(0x8000)
            a.ldh_a_n(STAT & 0xFF); a.and_n(3); a.ld_abs_a(0xC000)   # remember the mode we wrote in
            a.label("wait_vblank"); a.ldh_a_n(LY & 0xFF); a.cp_n(145); a.jr("wait_vblank", "nz")
            a.ld_r_n("a", 2); a.ld_abs_a(0x8001)
            a.ld_a_abs(0xFF69); a.ld_r_n("a", 3); a.ldh_n_a(0x69)         # palette write in VBlank: allowed
            a.label("done"); a.jr("done")
        rom, labels = micro_rom(program)
        cgb = CGB(rom, labels)
        cgb.run(until_pc=labels["done"], max_steps=200_000)
        self.assertEqual(cgb.read8(0xC000), 3, "the test program did not land in mode 3")
        self.assertEqual(cgb.mode3_vram_writes, 1)
        self.assertEqual(cgb.mode3_palette_writes, 0)
        self.assertEqual((cgb.vram[0][0], cgb.vram[0][1]), (1, 2))


class ConformanceGeneratorTests(unittest.TestCase):
    def test_micro_programs_assemble_run_and_dump_their_state(self):
        for seed in (1, 2, 3):
            rom, labels = harness_conformance.make_micro_rom(seed, 120)
            dump = harness_conformance.run_harness(rom, labels)
            self.assertEqual(dump[0xFF], 0xA5, "the program never reached its dump")
            self.assertEqual(dump[8] | dump[9] << 8, harness_conformance.STACK, "the stack was not balanced")
            self.assertEqual(dump[1] & 0x0F, 0, "F keeps its low nibble clear")
        self.assertNotEqual(harness_conformance.make_micro_rom(1, 120)[0], harness_conformance.make_micro_rom(2, 120)[0])

    def test_every_form_in_the_catalogue_is_reachable(self):
        import random
        seen = set()
        for seed in range(40):
            a = Assembler(origin=0x0150)
            rng = random.Random(seed)
            for _ in range(60):
                form = rng.choice(harness_conformance.FORMS)
                seen.add(form.__name__); form(a, rng, 0)
                a.labels.clear()
        self.assertEqual(seen, {form.__name__ for form in harness_conformance.FORMS})


if __name__ == "__main__":
    unittest.main()
