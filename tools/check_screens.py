#!/usr/bin/env python3
"""Every full-screen mode as the console draws it, checked against its golden.

Each screen is shown by the ROM's own `show_screen` on a machine that has
just reached the title, and captured from the emulated LCD: the title and
code entry, the ending and game over, the intermission, the episode pages
and every debrief. Runtime digit cells show the zeros power-on left them.
The captures are the `screens` snapshot suite (tools/snapshot.py); a changed
page fails naming the screen, and a deliberate change is accepted with a
note like any other golden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from sm83emu import CGB, parse_symbols  # noqa: E402


def capture_screens(rom: bytes, symbols: dict[str, int]):
    """(screen name, image) for every screen, in runtime order."""
    from lupine3d_v4.screens import SCREEN_SOURCES
    for index, (name, _, _, _) in enumerate(SCREEN_SOURCES):
        cgb = CGB(rom, symbols)
        cgb.button_provider = lambda *_: 0
        cgb.run(until_pc=symbols["title_screen"], max_steps=8_000_000)
        cgb.a = index
        cgb.call_subroutine("show_screen", max_steps=4_000_000)
        assert cgb.io[0x40] == 0x81, (name, hex(cgb.io[0x40]))
        yield name, cgb.render_screen()


def check(output: Path, snapshot_mode: str | None = "check") -> dict:
    rom_path, symbols_path = br.GAME_BUILD / "lupine3d.gb", br.GAME_BUILD / "lupine3d.sym"
    rom = rom_path.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    snapshots = None
    if snapshot_mode is not None:
        from snapshot import Suite, build_identity
        built_sha, configuration_id = build_identity()
        sha = hashlib.sha256(rom).hexdigest()
        snapshots = Suite("screens", mode=snapshot_mode, rom_sha256=sha,
                          configuration_id=configuration_id if built_sha == sha else "foreign-rom")
    names = []
    for name, image in capture_screens(rom, parse_symbols(symbols_path)):
        image.save(output / f"{name}.png")
        names.append(name)
        if snapshots is not None:
            snapshots.observe(name, image)
    report = {"schema": "lupine3d.screens.v1", "rom_sha256": hashlib.sha256(rom).hexdigest(),
              "screens": names, "passed": True}
    if snapshots is not None:
        report["snapshot"] = snapshots.report()
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if snapshots is not None:
        report["snapshot"] = snapshots.finish()   # raises in check mode when a screen differs
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=br.GAME_BUILD / "screens")
    parser.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check")
    args = parser.parse_args()
    report = check(args.output_dir, None if args.snapshot_mode == "none" else args.snapshot_mode)
    print(json.dumps({"screens": len(report["screens"]), "passed": report["passed"]}))


if __name__ == "__main__":
    main()
