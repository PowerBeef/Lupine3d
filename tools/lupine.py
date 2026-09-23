#!/usr/bin/env python3
"""`lupine`: one entry point for building, running and verifying Lupine 3D.

Every subcommand dispatches to the tool that owns the work, in a fresh
process with the profile flags set from the options, because the build
flags are read at import time (AGENTS.md). Nothing here changes what the
tools do; it only spares the reader the flag spelling and the script names.

    lupine build [--flat] [--display slim|compact|legacy] [--output-dir DIR]
    lupine run   [--scenario FILE] [--flat] [--snapshot-mode check|record|none]
    lupine snapshot diff|accept|list ... (tools/snapshot.py)
    lupine level check FILE...        compile a level and print its certificate
    lupine level info FILE            the level's contents at a glance
    lupine level export-tmx SRC DST   the level as a Tiled map (docs/LEVEL_FORMAT.md)
    lupine level import-tmx SRC DST   a Tiled map back to JSON, compiled to check it
    lupine profile [--flat]           cycles by main-loop stage on the coherence tour
    lupine test | witnesses | release-check | sable-check [--flat]
    lupine symbols [--flat]           where the debugger exports are and how to load them
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PROFILES = ("slim", "compact", "legacy")


def profile_env(args) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LUPINE3D_")}
    display = getattr(args, "display", None)
    if display:
        env["LUPINE3D_DISPLAY"] = display
        if display == "legacy":
            env.update(LUPINE3D_ART="legacy", LUPINE3D_ART_ANIMATION="0")
    if getattr(args, "flat", False):
        env["LUPINE3D_TEXTURED_WALLS"] = "0"
    return env


def run(command: list[str], env: dict[str, str]) -> int:
    print("$", " ".join(str(c) for c in command), flush=True)
    return subprocess.call([str(c) for c in command], cwd=ROOT, env=env)


def output_dir(args) -> Path:
    if getattr(args, "output_dir", None):
        return Path(args.output_dir)
    return ROOT / "build" / ("flat" if getattr(args, "flat", False) else "")


def rom_args(args) -> list[str]:
    out = output_dir(args)
    return ["--rom", out / "lupine3d.gb", "--symbols", out / "lupine3d.sym"]


def cmd_build(args) -> int:
    return run([sys.executable, TOOLS / "build_rom.py", "--output-dir", output_dir(args)], profile_env(args))


def cmd_run(args) -> int:
    command = [sys.executable, TOOLS / "playtest.py", *rom_args(args), "--snapshot-mode", args.snapshot_mode]
    if args.scenario:
        command += ["--scenario", args.scenario]
    if args.playtest_output:
        command += ["--output-dir", args.playtest_output]
    return run(command, profile_env(args))


def cmd_snapshot(args) -> int:
    return run([sys.executable, TOOLS / "snapshot.py", *args.rest], profile_env(args))


def cmd_level(args) -> int:
    sys.path.insert(0, str(TOOLS))
    from lupine3d_v4 import levels
    if args.action in ("export-tmx", "import-tmx"):
        from lupine3d_v4 import tmx_import
        if len(args.files) != 2:
            print(f"lupine level {args.action} SOURCE DESTINATION")
            return 2
        source, destination = Path(args.files[0]), Path(args.files[1])
        if args.action == "export-tmx":
            tmx_import.export_file(source, destination, swatch=args.swatch)
        else:
            tmx_import.import_file(source, destination)
            levels.compile_level(destination)
        print(f"{source} -> {destination}")
        return 0
    failures = 0
    for path in args.files:
        path = Path(path)
        try:
            level = levels.compile_level(path)
        except Exception as exc:  # the compiler's own message is the report
            print(f"{path}: REFUSED: {exc}")
            failures += 1
            continue
        segments = len(set(level.segment_table) - {0})
        report = level.readability
        if args.action == "check":
            print(f"{path}: ok - {level.name}: {level.width}x{level.height}, {len(level.doors)} doors, "
                  f"{len(level.entities)} actors, {len(level.pickups)} drops, {len(level.fixtures)} fixtures, "
                  f"{segments} segments")
            if report is not None:
                print(f"  certificate: {report.walkable_cells} walkable, {report.unreachable_cells} unreachable, "
                      f"critical path {report.critical_path_steps} steps/{report.critical_path_turns} turns, "
                      f"sightline {report.maximum_sightline}, room {report.maximum_open_rectangle[0]}x"
                      f"{report.maximum_open_rectangle[1]}, door separation {report.minimum_door_separation}, "
                      f"seams {report.material_seams}, singleton runs {report.material_singleton_runs}")
        else:
            source = json.loads(path.read_text())
            print(json.dumps({"name": level.name, "format": level.format, "size": [level.width, level.height],
                              "spawn": source.get("player_spawn"), "exit": {"x": level.exit.x, "y": level.exit.y},
                              "doors": [{"id": d.name, "x": d.x, "y": d.y, "flags": d.flags} for d in level.doors],
                              "actors": [{"kind": e.kind, "cell": [e.x_q8 >> 8, e.y_q8 >> 8], "health": e.health}
                                         for e in level.entities],
                              "drops": [{"kind": p.kind, "value": p.value} for p in level.pickups],
                              "fixtures": len(level.fixtures), "segments": segments,
                              "certificate": None if report is None else report.__dict__}, indent=2))
    return 1 if failures else 0


def cmd_profile(args) -> int:
    return run([sys.executable, TOOLS / "profile_rendering.py"], profile_env(args))


def cmd_test(args) -> int:
    return run(["make", "test"], profile_env(args))


def cmd_witnesses(args) -> int:
    command = [sys.executable, TOOLS / "independent_witnesses.py", "--snapshot-mode", args.snapshot_mode]
    if args.flat:
        command += ["--output-dir", ROOT / "build" / "independent-witnesses-flat"]
    return run(command, profile_env(args))


def cmd_release_check(args) -> int:
    return run([sys.executable, TOOLS / "release_check.py"], profile_env(args))


def cmd_sable_check(args) -> int:
    command = [sys.executable, TOOLS / "check_sable.py", "--snapshot-mode", args.snapshot_mode]
    if args.flat:
        command += ["--output-dir", ROOT / "build" / "sable-v2" / "flat-checks"]
    return run(command, profile_env(args))


def cmd_symbols(args) -> int:
    out = output_dir(args)
    manifest = out / "build_manifest.json"
    if not manifest.is_file():
        print(f"no build under {out}: run `lupine build{' --flat' if args.flat else ''}` first")
        return 1
    exports = json.loads(manifest.read_text()).get("exports")
    if not exports:
        print(f"the build under {out} predates the debugger exports: rebuild it first")
        return 1
    print(f"symbols: {out / 'lupine3d.sym'} ({exports.get('symbols')} entries: {exports.get('code')} code, "
          f"{exports.get('data')} data, {exports.get('ram')} RAM)")
    print(f"map:     {out / 'lupine3d.map'}")
    print("BGB: load the ROM, then Debug > Load symbols. Emulicious: place lupine3d.sym next to lupine3d.gb.")
    print("SameBoy: the debugger reads a .sym beside the ROM automatically.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lupine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def profile_options(p):
        p.add_argument("--flat", action="store_true", help="the flat-walled slim profile (LUPINE3D_TEXTURED_WALLS=0); textured walls are the slim default")
        p.add_argument("--display", choices=PROFILES, help="display profile; legacy implies legacy art")

    p = sub.add_parser("build", help="build the ROM, listing, symbols, map and manifest"); profile_options(p)
    p.add_argument("--output-dir", help="default build/, or build/flat with --flat"); p.set_defaults(func=cmd_build)
    p = sub.add_parser("run", help="run a driven scenario on the built ROM with every frame check"); profile_options(p)
    p.add_argument("--scenario"); p.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check")
    p.add_argument("--output-dir", dest="output_dir"); p.add_argument("--playtest-output"); p.set_defaults(func=cmd_run)
    p = sub.add_parser("snapshot", help="golden-image snapshots: run, diff, accept, list"); profile_options(p)
    p.add_argument("rest", nargs=argparse.REMAINDER); p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser("level", help="compile levels and print their certificates; convert to and from Tiled")
    p.add_argument("action", choices=("check", "info", "export-tmx", "import-tmx"))
    p.add_argument("files", nargs="+", help="levels to check, or SOURCE DESTINATION for a conversion")
    p.add_argument("--swatch", action="store_true", help="export-tmx: also write materials.png beside the map")
    p.set_defaults(func=cmd_level)
    p = sub.add_parser("profile", help="cycles by main-loop stage over the coherence tour"); profile_options(p); p.set_defaults(func=cmd_profile)
    p = sub.add_parser("test", help="the regression suite (make test)"); p.set_defaults(func=cmd_test)
    p = sub.add_parser("witnesses", help="frozen scenes in every pinned core against the goldens"); profile_options(p)
    p.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check"); p.set_defaults(func=cmd_witnesses)
    p = sub.add_parser("release-check", help="the release verification report"); p.set_defaults(func=cmd_release_check)
    p = sub.add_parser("sable-check", help="the emitted-ROM Sable qualification checks"); profile_options(p)
    p.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check"); p.set_defaults(func=cmd_sable_check)
    p = sub.add_parser("symbols", help="where the debugger exports are and how to load them"); profile_options(p)
    p.add_argument("--output-dir"); p.set_defaults(func=cmd_symbols)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
