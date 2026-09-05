"""Column kernels checked against arithmetic and the independent host oracle."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from sm83emu import CGB
from playtest import read_block


class ColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def boot(self):
        c = CGB(self.rom, self.asm.labels)
        c.run(until_pc=self.asm.labels["main_loop"])
        c.ime = False; c.write8(br.SIM_READY, 0)
        return c

    def test_stream_expansion_preserves_rounding_endpoints_and_array_bounds(self):
        c = self.boot(); rng = random.Random(705)
        arrays = ((br.RAY_STYLES, br.PIXEL_STYLES), (br.RAY_KEYS, br.PIXEL_KEYS),
                  (br.RAY_ALONG, br.PIXEL_ALONG), (br.RAY_SEGMENT, br.PIXEL_SEGMENT),
                  (br.RAY_SURFACE, br.PIXEL_SURFACE))
        for case in range(32):
            tops = [(case*8+i) & 255 for i in range(80)] if case < 16 else [rng.randrange(256) for _ in range(80)]
            for i, value in enumerate(tops): c.write8(br.RAY_TOPS+i, value)
            expected = []
            for i, value in enumerate(tops):
                for neighbour in (tops[max(0,i-1)], tops[min(79,i+1)]):
                    expected.append(((3*value+neighbour+2) & 255) >> 2)
            sources = {}
            for source, destination in arrays:
                sources[destination] = bytes(rng.randrange(256) for _ in range(80))
                for i, value in enumerate(sources[destination]): c.write8(source+i, value)
            c.write8(br.PIXEL_SURFACE+160, 0xA5)
            c.pc = self.asm.labels["build_pixel_descriptors"]
            c.run(until_pc=self.asm.labels["pixel_expansion_done"])
            self.assertEqual(read_block(c,br.PIXEL_TOPS,160),bytes(expected))
            for _, destination in arrays:
                self.assertEqual(read_block(c,destination,160),bytes(v for v in sources[destination] for _ in range(2)))
            self.assertEqual(c.read8(br.PIXEL_SURFACE+160),0xA5)

    def test_surface_scan_matches_oracle_for_boundaries_lod_and_door_runs(self):
        c = self.boot(); rng = random.Random(706)
        # First/last columns, every run length, page crossings, LOD thresholds,
        # adjacent different door keys and simultaneous physical/material edges.
        for case in range(200):
            tops = [rng.choice((0,31,32,33,40,41,47)) for _ in range(160)]
            styles = [rng.randrange(5) for _ in range(160)]
            keys = [0x20]*160; along = [3]*160; segments = [1]*160
            if case < 160:
                start, end = (0,case+1) if case & 1 else (159-case,160)
                keys[start:end] = [0x60+(i&1) for i in range(end-start)]
            else:
                keys = [rng.choice((0x20,0x40,0x60,0x61,0xE0)) for _ in range(160)]
                along = [rng.randrange(16) for _ in range(160)]
                segments = [rng.randrange(5) for _ in range(160)]
            want, events = br.decorate_surface_events(tops,styles,keys,along,segments)
            for address, values in ((br.PIXEL_TOPS,tops),(br.PIXEL_STYLES,styles),
                                    (br.PIXEL_KEYS,keys),(br.PIXEL_ALONG,along),(br.PIXEL_SEGMENT,segments)):
                for i, value in enumerate(values): c.write8(address+i,value)
            c.call_subroutine("decorate_pixel_styles")
            self.assertEqual(list(read_block(c,br.PIXEL_STYLES,160)),want,case)
            self.assertEqual(c.read8(br.EVENT_COUNT),events,case)
            self.assertEqual(c.read8(br.EVENT_INDEX),160)
