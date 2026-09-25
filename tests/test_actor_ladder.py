"""An enemy grows steadily as it comes closer.

The four distances' figures are 48, 32, 16 and 8 pixels tall in the showcase
and the starter (the close figure is half as tall again as the near one, then
each halves), and the engine switches where neighbouring sizes are equally
wrong, so nothing stays one size while the walls around it grow. Layout is
read at import time for the selected game, so each game is probed in a fresh
process.
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
from lupine3d_v4 import layout as l
heights, widths = l._actor_figure_heights()
print(json.dumps(dict(heights=heights, widths=widths, columns=l.SENTINEL_MID_COLUMNS,
                      close=l.ACTOR_CLOSE, lod=[l.LOD_CLOSE_ENTER, l.LOD_CLOSE_HOLD, l.LOD_NEAR_ENTER,
                                                l.LOD_NEAR_HOLD, l.LOD_FAR_HOLD, l.LOD_FAR_ENTER])))
"""


def probe(game):
    env = {k: v for k, v in os.environ.items() if not k.startswith('LUPINE3D_')}
    env.update(LUPINE3D_GAME=game, LUPINE3D_DISPLAY='slim', LUPINE3D_ART='sable-v2')
    result = subprocess.run([sys.executable, '-c', PROBE], env=env, cwd=ROOT, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


class ActorSizeLadder(unittest.TestCase):
    def check_game(self, game):
        data = probe(game)
        self.assertEqual(data['heights'], [48, 32, 16, 8], game)
        self.assertEqual(data['columns'], 1, game)
        self.assertTrue(data['close'], game)
        # Figures are true at forward 16 * 48 / h (Q4): 16, 24, 48 and 96, so
        # a wall one cell away (60 pixels) stands over a 48-pixel enemy. The
        # switches sit between them: close below 18 (held to 22), near below
        # 32 (held to 37), far from 73 (held down to 63).
        self.assertEqual(data['lod'], [18, 22, 32, 37, 63, 73], game)

    def test_showcase(self):
        self.check_game('games/sable_outpost')

    def test_starter(self):
        self.check_game('games/starter')

    def test_close_sheet_is_its_derivation(self):
        result = subprocess.run([sys.executable, 'games/sable_outpost/art/tools/derive_close_sentinel.py', '--check'],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        showcase, starter = (ROOT / game / 'art/native/sentinel_close.png' for game in ('games/sable_outpost', 'games/starter'))
        self.assertEqual(showcase.read_bytes(), starter.read_bytes())

    def test_distant_sheet_is_its_derivation(self):
        result = subprocess.run([sys.executable, 'games/sable_outpost/art/tools/derive_distant_sentinel.py', '--check'],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        showcase, starter = (ROOT / game / 'art/native/sentinel_distant.png' for game in ('games/sable_outpost', 'games/starter'))
        self.assertEqual(showcase.read_bytes(), starter.read_bytes())


if __name__ == '__main__':
    unittest.main()
