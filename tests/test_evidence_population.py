"""The evidence population: the engine's evidence keeps its v0.12 scene.

The showcase's first sector keeps its geometry; its population is the
game's to change. The engine's goldens, witnesses, cycle gates and sustained
tapes were recorded on the sector as v0.12 populated it, so a process run
with LUPINE3D_POPULATION=evidence swaps that population back in
(lupine3d_v4/levels.py). These tests hold the swap to its contract: the
frozen fields must agree, and the two images differ in one level slot and
the global checksum, never in code.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from lupine3d_v4 import levels  # noqa: E402
from lupine3d_v4.game import DEFAULT_GAME_DIR, load_game  # noqa: E402

SHOWCASE = load_game(DEFAULT_GAME_DIR)

BUILD = """
import hashlib, sys
sys.path.insert(0, 'tools')
import build_rom as br
rom, _, _ = br.make_rom()
open(sys.argv[1], 'wb').write(rom)
open(sys.argv[1] + '.evidence', 'wb').write(br.evidence_image(rom))
"""


class EvidencePopulation(unittest.TestCase):
    def test_the_fixture_keeps_the_shipped_sectors_frozen_fields(self):
        shipped = levels.compile_level(SHOWCASE.level_paths[0])
        frozen = levels.evidence_level(shipped)
        self.assertEqual(frozen, levels.compile_level(levels.EVIDENCE_LEVEL))
        self.assertEqual(levels.frozen_fields(frozen), levels.frozen_fields(shipped))

    def test_a_moved_wall_is_refused(self):
        source = json.loads(levels.EVIDENCE_LEVEL.read_text(encoding="utf-8"))
        rows = source["rows"]
        row = next(index for index, text in enumerate(rows) if "0" in text[1:-1] and 0 < index < 15)
        column = rows[row].index("0", 1)
        rows[row] = rows[row][:column] + "1" + rows[row][column + 1:]
        with tempfile.TemporaryDirectory() as scratch:
            moved = Path(scratch) / "moved.json"
            moved.write_text(json.dumps(source), encoding="utf-8")
            try:
                level = levels.compile_level(moved)
            except ValueError:
                self.skipTest("the probe wall broke the certificate before the population check")
            with self.assertRaisesRegex(ValueError, "frozen grid"):
                levels.evidence_level(level)

    def test_an_unknown_population_is_refused(self):
        previous = os.environ.get("LUPINE3D_POPULATION")
        os.environ["LUPINE3D_POPULATION"] = "museum"
        try:
            with self.assertRaisesRegex(ValueError, "shipped, evidence"):
                levels.population()
        finally:
            if previous is None:
                del os.environ["LUPINE3D_POPULATION"]
            else:
                os.environ["LUPINE3D_POPULATION"] = previous

    def test_the_populations_share_every_byte_but_one_level_slot(self):
        """Code never reads a sector's population at build time: the shipped
        and evidence builds of the default profile agree everywhere outside
        the first level slot and the global checksum."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("LUPINE3D_")}
        with tempfile.TemporaryDirectory() as scratch:
            outputs = {name: Path(scratch) / f"{name}.gb" for name in levels.POPULATIONS}
            children = [subprocess.Popen([sys.executable, "-c", BUILD, str(path)], cwd=ROOT,
                                         env={**env, "LUPINE3D_POPULATION": name})
                        for name, path in outputs.items()]
            for child in children:
                self.assertEqual(child.wait(timeout=900), 0)
            shipped, evidence = (outputs[name].read_bytes() for name in levels.POPULATIONS)
            # release_check's evidence SHA: a shipped process's own account of the evidence image.
            self.assertEqual(Path(str(outputs["shipped"]) + ".evidence").read_bytes(), evidence)
            self.assertEqual(Path(str(outputs["evidence"]) + ".evidence").read_bytes(), evidence)
        self.assertEqual(len(shipped), len(evidence))
        start = levels.level_rom_offset(0)
        end = start + levels.LEVEL_PAYLOAD_END - 0x4000
        outside = [offset for offset in range(len(shipped))
                   if shipped[offset] != evidence[offset] and not start <= offset < end and offset not in (0x014E, 0x014F)]
        self.assertEqual(outside, [])
        # The shipped image with the evidence slot written in is the evidence
        # image: release_check's evidence SHA is this construction.
        spliced = bytearray(shipped)
        spliced[start:end] = evidence[start:end]
        spliced[0x014E:0x0150] = evidence[0x014E:0x0150]
        self.assertEqual(bytes(spliced), evidence)


if __name__ == "__main__":
    unittest.main()
