"""The MBC5 bank contract: what the checker proves, and that it still bites."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4 import bank_safety  # noqa: E402
from lupine3d_v4.bank_safety import (  # noqa: E402
    FIXED_BANK_END, SWITCHABLE_END, BankSafetyError, analyze, entry_points,
)
from sm83 import Assembler  # noqa: E402


class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.metadata = br.make_rom()
        cls.report = analyze(cls.asm, entry_points(cls.asm, cls.rom))

    def test_the_built_image_satisfies_every_clause(self):
        self.assertEqual(self.report.violations, ())

    def test_entry_points_come_from_the_cartridge_vectors(self):
        points = entry_points(self.asm, self.rom)
        self.assertEqual(points["reset"], self.asm.origin)
        self.assertIn(self.asm.labels["vblank_isr"], points.values())
        # Every vector the cartridge installs is analysed; the rest are filler.
        installed = {vector for vector in range(0x0040, 0x0068, 8) if self.rom[vector] != 0xFF}
        self.assertEqual(len(points), len(installed) + 1)

    def test_every_bank_register_write_sits_in_the_fixed_half(self):
        self.assertTrue(self.report.bank_writes)
        for address in self.report.bank_writes:
            self.assertLess(address, FIXED_BANK_END, f"{address:04X} switches banks from the switchable half")

    def test_a_bank_window_never_runs_from_the_switchable_half(self):
        for address in self.report.tainted:
            self.assertLess(address, FIXED_BANK_END, f"{address:04X} runs with a foreign bank mapped")

    def test_the_interrupt_handlers_stay_fixed_and_never_switch_banks(self):
        self.assertTrue(self.report.interrupt)
        writes = set(self.report.bank_writes)
        for address in self.report.interrupt:
            self.assertLess(address, FIXED_BANK_END)
            self.assertNotIn(address, writes)

    def test_the_analysis_follows_every_transfer_in_the_image(self):
        # jp (hl) and rst would hide an edge; the engine emits neither.
        for instruction in self.report.instructions.values():
            self.assertNotIn(instruction.opcode, bank_safety._UNANALYSABLE, instruction.text)
        for target in self.report.external_targets:
            self.assertFalse(FIXED_BANK_END <= target < SWITCHABLE_END, f"${target:04X}")

    def test_no_section_falls_through_into_the_next(self):
        # This is what makes a section's address a placement decision, and so
        # what lets bank-neutral sections be emitted above $4000.
        self.assertGreater(len(self.asm.sections), 20)
        for violation in self.report.violations:
            self.assertNotIn("clause 6", violation)

    def test_cold_sections_really_did_land_above_the_bank_boundary(self):
        self.assertGreater(self.asm.labels["switchable_code"], FIXED_BANK_END)
        self.assertLess(self.asm.labels["resident_data"], FIXED_BANK_END)
        # The headroom the relocation bought, which is the point of all this.
        self.assertGreater(FIXED_BANK_END - self.asm.labels["resident_data"], 2048)

    def test_the_manifest_reports_what_was_proved(self):
        summary = self.metadata["bank_safety"]
        self.assertEqual(summary["bank_writes"], len(self.report.bank_writes))
        self.assertGreater(summary["instruction_bytes"], 10_000)
        self.assertLess(summary["pinned_bytes"], summary["instruction_bytes"])


class CheckerTests(unittest.TestCase):
    """The checker has to fail on images that break the rule it states."""

    @staticmethod
    def _image(build) -> tuple[Assembler, bytearray]:
        a = Assembler(origin=0x0150)
        build(a)
        rom = bytearray([0xFF] * 0x8000)
        rom[0x0100:0x0104] = bytes((0x00, 0xC3, 0x50, 0x01))
        code = a.resolve()
        rom[0x0150:0x0150 + len(code)] = code
        vblank = a.labels["vblank_isr"]
        rom[0x0040:0x0043] = bytes((0xC3, vblank & 0xFF, vblank >> 8))
        return a, rom

    @staticmethod
    def _prologue(a) -> None:
        a.section("reset")
        a.call("body")
        a.label("halt_loop"); a.jr("halt_loop")
        a.label("vblank_isr"); a.reti()
        a.section("body"); a.label("body")

    @staticmethod
    def _gap(a, target: int) -> None:
        """Filler up to an address, emitted as data so it is never decoded."""
        a.bytes(bytes(target - a.pc), "gap")

    def test_a_bank_write_above_the_boundary_is_refused(self):
        def build(a):
            self._prologue(a)
            a.ld_r_n("a", 2); a.ld_abs_a(0x2000)
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
            a.jp("high")
            self._gap(a, 0x4000)
            a.label("high")
            a.ld_r_n("a", 3); a.ld_abs_a(0x2000)
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 1" in v for v in report.violations), report.violations)

    def test_running_above_the_boundary_inside_a_window_is_refused(self):
        def build(a):
            self._prologue(a)
            a.ld_r_n("a", 2); a.ld_abs_a(0x2000)
            a.jp("high")
            self._gap(a, 0x4000)
            a.label("high")
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 2" in v for v in report.violations), report.violations)

    def test_a_window_that_escapes_a_return_still_taints_its_caller(self):
        def build(a):
            self._prologue(a)
            a.call("switch_and_return")
            a.jp("high")
            a.label("switch_and_return")
            a.ld_r_n("a", 2); a.ld_abs_a(0x2000); a.ret()
            self._gap(a, 0x4000)
            a.label("high")
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 2" in v for v in report.violations), report.violations)

    def test_a_window_closed_before_the_return_does_not_taint_its_caller(self):
        def build(a):
            self._prologue(a)
            a.call("switch_and_restore")
            a.jp("high")
            a.label("switch_and_restore")
            a.ld_r_n("a", 2); a.ld_abs_a(0x2000)
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()
            self._gap(a, 0x4000)
            a.label("high")
            a.ret()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertEqual(report.violations, ())

    def test_an_interrupt_handler_above_the_boundary_is_refused(self):
        def build(a):
            a.section("reset")
            a.call("body")
            a.label("halt_loop"); a.jr("halt_loop")
            a.section("body"); a.label("body")
            a.ret()
            self._gap(a, 0x4000)
            a.label("vblank_isr"); a.reti()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 3" in v for v in report.violations), report.violations)

    def test_an_interrupt_handler_that_switches_banks_is_refused(self):
        def build(a):
            a.section("reset")
            a.call("body")
            a.label("halt_loop"); a.jr("halt_loop")
            a.label("vblank_isr")
            a.ld_r_n("a", 2); a.ld_abs_a(0x2000)
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.reti()
            a.section("body"); a.label("body")
            a.ret()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 3" in v for v in report.violations), report.violations)

    def test_a_section_that_can_be_fallen_into_is_refused(self):
        def build(a):
            a.section("reset")
            a.call("body")
            a.label("halt_loop"); a.jr("halt_loop")
            a.label("vblank_isr"); a.reti()
            a.section("body"); a.label("body")
            a.nop()                     # no ret: the next section is fallen into
            a.section("tail")
            a.ret()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 6" in v for v in report.violations), report.violations)

    def test_an_unfollowable_transfer_is_refused(self):
        def build(a):
            a.section("reset")
            a.call("body")
            a.label("halt_loop"); a.jr("halt_loop")
            a.label("vblank_isr"); a.reti()
            a.section("body"); a.label("body")
            a.jp_hl()
        asm, rom = self._image(build)
        report = analyze(asm, entry_points(asm, rom))
        self.assertTrue(any("clause 4" in v for v in report.violations), report.violations)

    def test_check_bank_safety_raises_rather_than_returning_a_bad_image(self):
        def build(a):
            self._prologue(a)
            a.ld_r_n("a", 2); a.ld_abs_a(0x2000)
            a.jp("high")
            self._gap(a, 0x4000)
            a.label("high")
            a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()
        asm, rom = self._image(build)
        with self.assertRaises(BankSafetyError):
            bank_safety.check_bank_safety(asm, rom)


if __name__ == "__main__":
    unittest.main()
