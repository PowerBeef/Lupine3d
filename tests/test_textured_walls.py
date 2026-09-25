"""The textured profile's emitted kernel, in a fresh process.

`LUPINE3D_TEXTURED_WALLS=1` is a rendering profile, so it is read at import
time like the display and art profiles: this lane builds that ROM in its own
process and runs the Sable qualification checks against it. Those checks
drive the kernel blind through far walls in the self-mirrored centre tile, a
seam with a decorated pixel and a full-height wall that laps the 96-slot ring
and crosses the VRAM half, then compare every pattern in both banks with the
reference kernel; they also exercise the ring-wrapping publication windows
and the chunked HBlank hand-off, and validate six poses frame by frame.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TexturedWallsLane(unittest.TestCase):
    def test_reference_tests_pass_on_the_slim_viewport(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('LUPINE3D_')}
        env.update(LUPINE3D_DISPLAY='slim', LUPINE3D_ART='sable-v2', LUPINE3D_POPULATION='evidence')
        result = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_texture_reference', '-v'],
                                env=env, cwd=ROOT, capture_output=True, text=True, timeout=900)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        self.assertNotIn('skipped', result.stderr)

    def test_textured_kernel_qualifies_in_a_fresh_process(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('LUPINE3D_')}
        env.update(LUPINE3D_DISPLAY='slim', LUPINE3D_ART='sable-v2', LUPINE3D_TEXTURED_WALLS='1')
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(ROOT / 'tools/check_sable.py'), '--snapshot-mode', 'none',
                                     '--output-dir', directory], env=env, cwd=ROOT, capture_output=True, text=True, timeout=1500)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
            checks = json.loads((Path(directory) / 'checks.json').read_text())
            self.assertTrue(checks['passed'])
            self.assertTrue(checks['configuration']['textured_walls'])
            for name in ('texture_window_blocks_and_directory', 'texture_sets_per_episode',
                         'pixel_u_expansion_every_difference',
                         'textured_blind_composition_ring_lap_and_vram_half',
                         'publication_cpu_and_dma_windows', 'hblank_streaming_bank_isolation_and_chaining',
                         'geometry_and_all_published_rows'):
                self.assertTrue(checks['checks'][name], name)
            self.assertTrue(any(w['dynamic'] == 160 for w in checks['publication_windows']))


if __name__ == '__main__':
    unittest.main()
