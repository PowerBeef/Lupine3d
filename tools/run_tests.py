#!/usr/bin/env python3
"""Run frozen engine regressions plus fresh-process production-art checks.

Historical arithmetic/image tests intentionally use the original 96-line
profile. test_sable_v2 launches separate clean processes for the current
production defaults, emitted HUD/animation/publication and both display modes.
No test process changes the caller's build configuration or output ROM.
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('LUPINE3D_')}
    env.update(LUPINE3D_DISPLAY='legacy', LUPINE3D_ART='legacy',
               LUPINE3D_ART_ANIMATION='0')
    return subprocess.call([sys.executable, '-m', 'unittest', 'discover',
                            '-s', 'tests', '-v'],
                           cwd=Path(__file__).resolve().parents[1], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
