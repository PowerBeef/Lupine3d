"""The projected-top to depth certificate never lets a near wall read as far.

A reconstructed midpoint sample takes its occlusion depth from its projected
top through `top_depth_lut`. Close to a wall the projected half-height jumps
several pixels for one Q5 depth step, so some tops belong to no depth; an
empty top used to read 255, infinitely far, and an enemy behind that wall
showed through it. The table is read at import time for the display profile,
so each profile is checked in a fresh process.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROBE = """
import json, sys
sys.path.insert(0, 'tools')
from lupine3d_v4.layout import HORIZON
from lupine3d_v4.resources import make_tables, make_top_depth_lut
projection = make_tables()['projection_half']
classes = {}
for depth, half in enumerate(projection):
    classes.setdefault(HORIZON - half, []).append(depth)
print(json.dumps(dict(lut=list(make_top_depth_lut()), classes={str(k): v for k, v in classes.items()})))
"""


def probe(**flags):
    env = {k: v for k, v in os.environ.items() if not k.startswith('LUPINE3D_')}
    env.update(flags)
    result = subprocess.run([sys.executable, '-c', PROBE], env=env, cwd=ROOT, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])
    data = json.loads(result.stdout.strip().splitlines()[-1])
    return data['lut'], {int(k): v for k, v in data['classes'].items()}


class TopDepthCertificate(unittest.TestCase):
    def check_profile(self, **flags):
        lut, classes = probe(**flags)
        farthest = max(classes)
        for top in range(farthest + 1):
            if top in classes:
                # A top some depth projects to keeps its nearest member.
                self.assertEqual(lut[top], min(255, min(classes[top])), (flags, top))
            # No top reads farther than any wall that projects at or beyond it.
            beyond = [min(depths) for t, depths in classes.items() if t >= top]
            self.assertLessEqual(lut[top], min(255, min(beyond)), (flags, top))
            if top:
                self.assertLessEqual(lut[top - 1], lut[top], (flags, top))

    def test_slim_has_no_far_holes(self):
        self.check_profile(LUPINE3D_DISPLAY='slim', LUPINE3D_ART='sable-v2')

    def test_compact_has_no_far_holes(self):
        self.check_profile(LUPINE3D_DISPLAY='compact', LUPINE3D_ART='sable-v2')


if __name__ == '__main__':
    unittest.main()
