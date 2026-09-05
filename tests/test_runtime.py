"""Exact arithmetic and continuation checks for the gameplay performance pass."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from lupine3d_v4.precision import q14_direction
from sm83emu import CGB


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def boot(self):
        c = CGB(self.rom, self.asm.labels)
        c.run(until_pc=self.asm.labels["main_loop"])
        c.ime = False
        c.write8(br.SIM_READY, 0)
        return c

    def test_bounded_division_quotient_remainder_and_overflow_contract(self):
        c = self.boot()
        rng = random.Random(703)
        divisors = sorted({1, 3, 127, 255, 257, 16383, 16384, 32767, 32768, 65535,
                           *(1 << bit for bit in range(16))})
        cases = [(q * d + r, d) for d in divisors
                 for q in (0, 1, 255, 256, 4095, 4096, 32767, 65535)
                 for r in (0, d - 1)]
        cases += [(rng.randrange(1 << 32), rng.randrange(1, 65536)) for _ in range(512)]
        cases += [(d << 16, d) for d in divisors] + [(123456, 0)]
        for numerator, divisor in cases:
            c.write16(br.Q14_PRODUCT, numerator & 65535)
            c.write16(br.Q14_PRODUCT + 2, numerator >> 16)
            c.d, c.e = divisor >> 8, divisor & 255
            c.call_subroutine("divide_u32_u16_bounded")
            actual = c.read16(br.Q14_PRODUCT) | c.read16(br.Q14_PRODUCT + 2) << 16
            if numerator >> 16 >= divisor:
                self.assertEqual(actual, numerator, (numerator, divisor))
            else:
                self.assertEqual((actual, c.hl), divmod(numerator, divisor), (numerator, divisor))
            self.assertEqual((c.d << 8) | c.e, divisor)

    def test_product_lookup_covers_every_bank_selector_and_restores_bank_one(self):
        c = self.boot()
        for right in range(256):
            for left in (0, 1, 127, 128, 255):
                c.b, c.c = left, right
                c.call_subroutine("mul_u8")
                self.assertEqual(c.hl, left * right, (left, right))
                self.assertEqual(c.rom_bank, 1)

    def test_continuations_equal_full_q14_restarts_after_certified_crossings(self):
        c = self.boot()
        rng = random.Random(714)
        # Open interior forces late uncertain crossings instead of immediately
        # terminating at the small playable level's nearest wall.
        for y in range(16):
            for x in range(16):
                c.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
        c.write8(br.WORLD_MODE, 0)
        resumed_late = 0
        original_step = c.step
        def observe():
            nonlocal resumed_late
            if c.pc == self.asm.labels["q14_resume"] and c.read8(br.DDA_CROSSINGS) >= 2:
                resumed_late += 1
            return original_step()
        c.step = observe
        addresses = (br.DDA_MAP_X, br.DDA_MAP_Y, br.DDA_AXIS, br.DDA_DIST_L,
                     br.DDA_DIST_H, br.DDA_MATERIAL, br.DDA_CROSSINGS)
        for _ in range(512):
            x, y = rng.randrange(256, 15 * 256), rng.randrange(256, 15 * 256)
            angle, column = rng.randrange(256), rng.randrange(160)
            c.write16(br.PLAYER_XL, x); c.write16(br.PLAYER_YL, y)
            c.write8(br.ANGLE, angle); c.write8(br.PIXEL_INDEX, column)
            c.call_subroutine("cast_physical_indexed")
            # Certain rays may intentionally keep coarse ordering/projection.
            if not c.read8(br.Q14_ACTIVE):
                continue
            expected = tuple(c.read8(address) for address in addresses)
            c.write8(br.Q14_RECORD, column + 80)  # projection closes the indexed ABI
            c.call_subroutine("q14_restart")
            self.assertEqual(tuple(c.read8(address) for address in addresses), expected,
                             (x, y, angle, column, q14_direction(angle, column + 80)))
        self.assertGreater(resumed_late, 32, "corpus must exercise continuation after multiple cells")
