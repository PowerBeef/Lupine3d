"""Linked-code and allocation contracts for the rendering review sequence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from lupine3d_v4.allocation import Allocation, validate_allocations
from lupine3d_v4.configuration import resolve, FLAGS
from runtime_observer import RuntimeObserver, distribution
from sm83emu import CGB


def variant(**flags):
    """Resolve import-time configuration in a fresh process, as in production."""
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ, **{"LUPINE3D_"+flag:"0" for flag in FLAGS.values()},LUPINE3D_PROJECTION_STORAGE="direct")
        env.update({"LUPINE3D_" + name: str(value) for name, value in flags.items()})
        subprocess.run([sys.executable, "-c", "import sys,json;from pathlib import Path;"
                        "sys.path.insert(0,'tools');import build_rom as b;"
                        "r,a,m=b.make_rom();p=Path(sys.argv[1]);"
                        "(p/'rom').write_bytes(r);(p/'metadata').write_text(json.dumps([a.labels,m]))", folder],
                       cwd=br.ROOT, env=env, check=True, capture_output=True)
        labels, metadata = json.loads((Path(folder) / "metadata").read_text())
        return (Path(folder) / "rom").read_bytes(), labels, metadata


class StripExperiments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compact = variant(COMPACT_STRIPS=1, FOLDED=1)
        cls.general = variant(COMPACT_STRIPS=0, FOLDED=0)
        cls.legacy = variant(COMPACT_STRIPS=0, FOLDED=1)

    def test_all_282_folded_selectors_and_6768_patterns(self):
        rom, labels, metadata = self.compact
        c = CGB(rom, labels)
        logical = br.FOLDED_STORED_STATES
        singles, pairs = br.make_microstrips(), br.make_pair_microstrips()
        cases = patterns = 0
        for top in range(47):
            for y in range(0, 48, 8):
                c.write8(br.TILE_Y0, y); c.a = top
                c.call_subroutine("compute_strip_state")
                expected = 0 if y + 7 < top else 1 if y >= top else top - y + 1
                self.assertEqual(c.a, expected, (top, y))
                state = c.a; cases += 1
                for style in range(2):
                    for fn, table, width in (("get_microstrip_ptr", singles, 8), ("get_pair_microstrip_ptr", pairs, 4)):
                        for pixel in range(width):
                            c.write8(br.STRIP_STATE, state); c.write8(br.STRIP_STYLE, style)
                            c.write8(br.STRIP_PAIR, pixel if width == 8 else pixel * 2)
                            c.call_subroutine(fn)
                            base = ((style * 19 + logical[state]) * width + pixel) * 16
                            self.assertEqual(bytes(c.read8(c.hl + j) for j in range(16)), table[base:base+16])
                            self.assertEqual(c.rom_bank, 1)
                            patterns += 1
        self.assertEqual((cases, patterns), (282, 6768))
        self.assertEqual(metadata["microstrip_format"]["table_bytes_saved"], 3840)
        self.assertEqual(metadata["memory_budget"]["resident_free_bytes"],
                         self.legacy[2]["memory_budget"]["resident_free_bytes"] + 3840)

    def test_entire_banked_oracle_and_unfolded_selector_domain(self):
        c = CGB(self.general[0], self.general[1])
        tables = (("get_microstrip_ptr", br.make_microstrips(), 8),
                  ("get_pair_microstrip_ptr", br.make_pair_microstrips(), 4))
        for fn, table, width in tables:
            for style in range(2):
                for state in range(19):
                    for pixel in range(width):
                        c.write8(br.STRIP_STYLE, style); c.write8(br.STRIP_STATE, state)
                        c.write8(br.STRIP_PAIR, pixel if width == 8 else pixel * 2)
                        c.call_subroutine(fn)
                        base = ((style * 19 + state) * width + pixel) * 16
                        self.assertEqual(c.hl, br.STRIP_SCRATCH)
                        self.assertEqual(bytes(c.read8(c.hl+j) for j in range(16)), table[base:base+16])
                        self.assertEqual(c.rom_bank, 1)
        for top in range(47):
            for y in range(0, 96, 8):
                c.write8(br.TILE_Y0, y); c.a = top; c.call_subroutine("compute_strip_state")
                bottom = 96 - top
                expected = (0 if y+7 < top else 1 if y >= bottom else top-y+3 if y < top
                            else 2 if y+7 < bottom else bottom-y+10)
                self.assertEqual(c.a, expected, (top, y))


class ObservationContracts(unittest.TestCase):
    def test_observation_preserves_cycles_state_and_image(self):
        rom, asm, _ = br.make_rom()
        plain, observed = (CGB(rom, asm.labels) for _ in range(2))
        for c in (plain, observed):
            c.run(until_pc=asm.labels["main_loop"])
            c.button_provider = lambda *_: 1
        observer = RuntimeObserver(observed)
        for c in (plain, observed): c.run(until_presentations=3)
        report = observer.report()
        self.assertEqual(plain.cycles, observed.cycles)
        self.assertEqual(plain.wram0, observed.wram0)
        self.assertEqual(plain.wramx, observed.wramx)
        self.assertEqual(plain.render_screen().tobytes(), observed.render_screen().tobytes())
        self.assertEqual(sum(report["exclusive_cycles"].values()), report["elapsed_cycles"])
        self.assertEqual(report["game_ram_writes_after_trial_start"], 0)
        self.assertTrue(all(report["exclusive_cycles"].values()))
        self.assertTrue(report["events"])

    def test_percentile_and_configuration_fail_closed(self):
        self.assertEqual(distribution(range(1, 101))["p95"], 95)
        self.assertIsNone(distribution([])["mean"])
        for flags in ({"LUPINE3D_COMPACT_STRIPS": "yes"},
                      {"LUPINE3D_COMPACT_STRIPS": "1", "LUPINE3D_FOLDED": "0"},
                      {"LUPINE3D_PROJECTION_STORAGE": "unknown"}):
            with self.assertRaises(ValueError): resolve(flags)

    def test_allocation_overlaps_are_rejected_even_for_distinct_lifetimes(self):
        rows = [Allocation("WRAM1", 0xDF42, 0xDF56, "validity"),
                Allocation("WRAM1", 0xDF55, 0xDF60, "unexpected", "scratch")]
        with self.assertRaises(AssertionError): validate_allocations(rows)
        validate_allocations([rows[0], Allocation("WRAM3", 0xDF42, 0xDF56, "banked")])

    def test_production_defaults_preserve_historical_diagnostic_commands(self):
        self.assertEqual({k for k,v in resolve({}).items() if v is True},
                         {"compact_strips", "camera_setup", "narrow_yields", "attribute_padding", "art_animation"})
        for legacy, experiment in (("FOLDED", "COMPACT_STRIPS"),
                                   ("PREPARED_RAYS", "CAMERA_SETUP"),
                                   ("REPROJECTION", "NARROW_YIELDS")):
            value = "1" if legacy == "REPROJECTION" else "0"
            self.assertFalse(resolve({"LUPINE3D_"+legacy:value})[experiment.lower()])
            with self.assertRaises(ValueError):
                resolve({"LUPINE3D_"+legacy:value, "LUPINE3D_"+experiment:"1"})


if __name__ == "__main__": unittest.main()
