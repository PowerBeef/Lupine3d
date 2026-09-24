#!/usr/bin/env python3
"""Prove that a refactor leaves every ROM the engine builds byte-identical.

A refactor that is meant to change no behaviour must change no ROM byte, in
any configuration the project builds: the default textured slim build and
its synchronous tail, the historical compact and legacy profiles, the exact
A/B variants and the single-level fixtures. Identical ROM bytes also keep
every piece of retained evidence valid, because the route, core, witness and
sustained reports are bound to the ROM's SHA-256.

    python tools/rom_identity.py compare --base origin/main      # make identity BASE=…
    python tools/rom_identity.py record --output build/identity.json --source /path/to/clean/copy
    python tools/rom_identity.py check build/identity.json

`compare` builds a git ref in a clean copy and this checkout; `record` and
`check` pin a set of ROMs across a longer series of changes (the game/engine
separation was proven that way, commit by commit).

Each configuration builds in a fresh process (flags are read at import time)
with every inherited `LUPINE3D_*` variable removed, through
`tools/build_rom.py --output-dir`, several at once. The `.gb` SHA-256 is the
gate. The configuration id and the symbol file are reported as well: a
difference there with identical ROM bytes (a renamed label, say) is shown
but does not fail the check.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# name -> environment. A `level:` value names a level fixture, found in the
# source tree being built (tests/levels/ first, then levels/), so the same
# table describes a tree before and after the fixtures move.
CONFIGURATIONS: dict[str, dict[str, str]] = {
    "default": {},
    "sync": {"LUPINE3D_OVERLAP_PUBLICATION": "0"},
    "compact": {"LUPINE3D_DISPLAY": "compact"},
    "compact-unfolded": {"LUPINE3D_DISPLAY": "compact", "LUPINE3D_FOLDED": "0", "LUPINE3D_COMPACT_STRIPS": "0"},
    "legacy": {"LUPINE3D_DISPLAY": "legacy", "LUPINE3D_ART": "legacy", "LUPINE3D_ART_ANIMATION": "0"},
    "reprojection": {"LUPINE3D_REPROJECTION": "1", "LUPINE3D_NARROW_YIELDS": "0"},
    "reuse-disabled": {"LUPINE3D_WALL_REUSE": "0"},
    "prepared-disabled": {"LUPINE3D_PREPARED_RAYS": "0", "LUPINE3D_CAMERA_SETUP": "0"},
    "two-sentinels": {"LUPINE3D_LEVEL": "level:two_sentinels"},
    "renderer-benchmark": {"LUPINE3D_LEVEL": "level:renderer_benchmark"},
}
SCHEMA = "lupine3d.rom-identity.v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_env(source: Path, env: dict[str, str]) -> dict[str, str]:
    resolved = {}
    for key, value in env.items():
        if value.startswith("level:"):
            name = value[len("level:"):] + ".json"
            for candidate in (source / "tests" / "levels" / name, source / "levels" / name):
                if candidate.is_file():
                    value = str(candidate)
                    break
            else:
                raise SystemExit(f"{key}: no level fixture {name} under {source}/tests/levels or {source}/levels")
        resolved[key] = value
    return resolved


def build_one(source: Path, name: str, output: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("LUPINE3D_")}
    env.update(resolve_env(source, CONFIGURATIONS[name]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    target = output / name
    started = time.monotonic()
    completed = subprocess.run([sys.executable, str(source / "tools" / "build_rom.py"), "--output-dir", str(target)],
                               cwd=source, env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        raise SystemExit(f"{name}: the build failed\n{completed.stdout[-2000:]}{completed.stderr[-4000:]}")
    manifest = json.loads((target / "build_manifest.json").read_text(encoding="utf-8"))
    return {
        "env": CONFIGURATIONS[name],
        "rom_sha256": sha256(target / "lupine3d.gb"),
        "configuration_id": manifest.get("configuration_id"),
        "sym_sha256": sha256(target / "lupine3d.sym"),
        "seconds": round(time.monotonic() - started, 1),
    }


def build_all(source: Path, output: Path, names: list[str], jobs: int) -> dict[str, dict]:
    output.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(build_one, source, name, output): name for name in names}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            results[name] = future.result()
            print(f"  built {name:<20} {results[name]['rom_sha256'][:12]}  {results[name]['seconds']:6.1f} s", flush=True)
    return {name: results[name] for name in names}


def git_head(source: Path) -> str | None:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True)
    return completed.stdout.strip() if completed.returncode == 0 else None


def compare(expected: dict[str, dict], actual: dict[str, dict]) -> bool:
    identical = True
    for name, want in expected.items():
        got = actual.get(name)
        if got is None:
            print(f"  MISSING   {name}")
            identical = False
            continue
        if got["rom_sha256"] != want["rom_sha256"]:
            print(f"  CHANGED   {name}: ROM {want['rom_sha256'][:12]} -> {got['rom_sha256'][:12]}")
            identical = False
            continue
        notes = []
        if got["configuration_id"] != want["configuration_id"]:
            notes.append(f"configuration id {want['configuration_id']} -> {got['configuration_id']}")
        if got["sym_sha256"] != want["sym_sha256"]:
            notes.append("symbol file differs")
        print(f"  identical {name}" + (f" (ROM bytes equal; {'; '.join(notes)})" if notes else ""))
    return identical


def archive(ref: str, destination: Path) -> None:
    listing = subprocess.run(["git", "archive", "--format=tar", ref], cwd=ROOT, capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(destination)], input=listing.stdout, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", help="build every configuration and write the SHA-256 record")
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--source", type=Path, default=ROOT, help="the source tree to build (default: this checkout)")
    record.add_argument("--commit", help="the commit the source tree is (a git archive has no .git to ask)")
    check = sub.add_parser("check", help="build this checkout and compare with a record")
    check.add_argument("record", type=Path)
    versus = sub.add_parser("compare", help="build a git ref and this checkout and compare them")
    versus.add_argument("--base", required=True, help="a git ref, e.g. origin/main or HEAD~1")
    for p in (record, check, versus):
        p.add_argument("--only", help="comma-separated configurations (default: all)")
        p.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    args = parser.parse_args(argv)

    names = [n.strip() for n in args.only.split(",")] if args.only else list(CONFIGURATIONS)
    unknown = [n for n in names if n not in CONFIGURATIONS]
    if unknown:
        raise SystemExit(f"unknown configurations {unknown}; known: {', '.join(CONFIGURATIONS)}")

    with tempfile.TemporaryDirectory(prefix="rom-identity-") as scratch:
        scratch_path = Path(scratch)
        if args.command == "record":
            source = args.source.resolve()
            print(f"recording {len(names)} configuration(s) from {source}")
            results = build_all(source, scratch_path / "out", names, args.jobs)
            payload = {"schema": SCHEMA, "source_commit": args.commit or git_head(source), "configurations": results}
            for result in results.values():
                result.pop("seconds", None)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {args.output}")
            return 0
        if args.command == "check":
            expected = json.loads(args.record.read_text(encoding="utf-8"))
            if expected.get("schema") != SCHEMA:
                raise SystemExit(f"{args.record} is not a {SCHEMA} record")
            want = {n: expected["configurations"][n] for n in names if n in expected["configurations"]}
            print(f"checking {len(want)} configuration(s) against {args.record} (recorded at {expected.get('source_commit')})")
            actual = build_all(ROOT, scratch_path / "out", list(want), args.jobs)
        else:
            base = scratch_path / "base"
            base.mkdir()
            archive(args.base, base)
            print(f"building {len(names)} configuration(s) at {args.base} and in this checkout")
            want = build_all(base, scratch_path / "base-out", names, args.jobs)
            actual = build_all(ROOT, scratch_path / "out", names, args.jobs)
        identical = compare(want, actual)
    print("IDENTICAL: every ROM is byte-for-byte unchanged" if identical else "FAILED: a ROM changed")
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
