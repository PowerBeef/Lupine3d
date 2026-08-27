#!/usr/bin/env python3
"""Create and validate the Lupine 3D Python development environment."""
from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv")
    parser.add_argument("--offline", action="store_true", help="reuse system site packages and never invoke pip")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args()

    python = venv_python(args.venv)
    if not python.exists():
        venv.EnvBuilder(with_pip=True, system_site_packages=args.offline).create(args.venv)
    try:
        subprocess.run([str(python), "-c", "from PIL import Image; print('Pillow import: OK')"], check=True)
    except subprocess.CalledProcessError:
        if args.offline:
            raise SystemExit("Pillow is unavailable offline; install requirements first")
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)

    if not args.skip_smoke:
        subprocess.run([str(python), str(ROOT / "tools" / "build_rom.py")], cwd=ROOT, check=True)
        subprocess.run([
            str(python), "-m", "unittest", "discover", "-s", "tests", "-p", "test_engine.py",
        ], cwd=ROOT, check=True)
    print(f"Development environment ready: {python}")


if __name__ == "__main__":
    main()
