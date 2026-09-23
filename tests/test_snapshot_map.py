"""The render snapshot copies the 256-byte map only when the live map's
generation moved. Every live map writer bumps it, so at the end of every
snapshot the bank-1 map must equal the bank-2 map, through door openings in
both world modes and without the pose injections' help."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_rom as br  # noqa: E402
from playtest import apply_diagnostic_camera, button_mask, set_test_world_byte  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402


@unittest.skipUnless(br.FIXED_SIMULATION, "the snapshot exists only with fixed-tick simulation")
class SnapshotMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def run_door(self, world_mode: int) -> tuple[int, int, int]:
        cgb = CGB(self.rom, self.asm.labels)
        run_to_world(cgb)
        set_test_world_byte(cgb, br.WORLD_MODE, world_mode)
        done = self.asm.labels["snapshot_copied"]
        checks = {"snapshots": 0, "map_copies": 0}
        last = [cgb.read8(br.SNAP_MAP_GEN)]
        original = cgb.step

        def step():
            if cgb.pc == done:
                checks["snapshots"] += 1
                self.assertEqual(bytes(cgb.wramx[1][:256]), bytes(cgb.wramx[2][:256]),
                                 "the snapshot map differs from the live map")
                generation = cgb.read8(br.SNAP_MAP_GEN)
                self.assertEqual(generation, cgb.read8(br.LIVE_MAP_GEN))
                if generation != last[0]:
                    checks["map_copies"] += 1
                    last[0] = generation
            return original()
        cgb.step = step
        # Face the airlock door two cells ahead of the spawn and press B.
        apply_diagnostic_camera(cgb, {"pose": [1152, 3136, 192]})
        cgb.button_provider = lambda *_: button_mask(["b"])
        cgb.run(until_presentations=cgb.presentations + 2)
        cgb.button_provider = lambda *_: 0
        cgb.run(until_presentations=cgb.presentations + 20)
        door_cell = cgb.wramx[2][11 * 16 + 4]
        return checks["snapshots"], checks["map_copies"], door_cell

    def test_the_living_door_reaches_the_snapshot_when_it_opens(self):
        snapshots, copies, door_cell = self.run_door(1)
        self.assertEqual(door_cell, 0, "the airlock door did not open")
        self.assertGreater(snapshots, 10)
        self.assertEqual(copies, 1, "exactly the door's completion moves the map")

    def test_the_instant_door_of_the_empty_world_reaches_the_snapshot(self):
        snapshots, copies, door_cell = self.run_door(0)
        self.assertEqual(door_cell, 0)
        self.assertGreater(snapshots, 10)
        self.assertEqual(copies, 1)


if __name__ == "__main__":
    unittest.main()
