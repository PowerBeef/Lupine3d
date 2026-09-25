#!/usr/bin/env python3
"""Run frozen engine regressions plus fresh-process production-art checks.

Historical arithmetic/image tests intentionally use the original 96-line
profile. test_sable_v2 launches separate clean processes for the current
production defaults, emitted HUD/animation/publication and both display modes.
No test process changes the caller's build configuration or output ROM.
Every LUPINE3D_* variable is dropped first, LUPINE3D_GAME included, so the
suite always tests the engine on the showcase game, and on the evidence
population: the showcase's first sector as v0.12 populated it
(lupine3d_v4/levels.py), the scene the engine's tests were written against.
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('LUPINE3D_')}
    env.update(LUPINE3D_DISPLAY='legacy', LUPINE3D_ART='legacy',
               LUPINE3D_ART_ANIMATION='0', LUPINE3D_POPULATION='evidence')
    return subprocess.call([sys.executable, '-m', 'unittest', 'discover',
                            '-s', 'tests', '-v'],
                           cwd=Path(__file__).resolve().parents[1], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
