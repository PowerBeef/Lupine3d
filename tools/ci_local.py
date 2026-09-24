#!/usr/bin/env python3
"""Run CI's jobs locally, in parallel, before a push.

Every lane of `tools/ci_lanes.py` (the jobs `.github/workflows/ci.yml` runs,
the route in its chunks) runs in its own copy of the working tree, the way
each CI job gets its own runner: lanes cannot share `build/`, because they
rebuild the ROM and rewrite the same reports. A copy holds exactly the files
a commit would (`git ls-files` tracked plus untracked-not-ignored, as they
stand in the working tree); the caller's `LUPINE3D_*` flags are dropped, so a
lane builds the default configuration as CI does.

    python tools/ci_local.py                 # every lane, one per CPU
    python tools/ci_local.py --changed       # only what the change needs
    python tools/ci_local.py --lanes fast,route-10-10 --jobs 2
    python tools/ci_local.py --list
    python tools/ci_local.py --changed --dry-run

`--changed` compares with `origin/main` (or `--base`): a change to
documentation alone runs `make docs-check`; anything else runs every lane.
Each lane stops at its first failing command. Logs and each lane's tree are
under `build/ci-local/`; route reports are copied back into `build/` so
`tools/release_check.py` can union them. The summary fails if any lane
failed, if a lane was skipped (the slow lane needs the pinned cores under
`build/deps`, docs/DEVELOPMENT.md), or if the lanes did not all build the
same ROM.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from ci_lanes import CORE_LANES, MGBA_DIR, ROUTE_CHUNKS, SAMEBOY_DIR, all_lanes, route_lane_name  # noqa: E402

DOCS_LANE = {"docs": [["make", "docs-check"]]}
# Rough CI minutes, used only to start the longest lanes first.
EXPECTED_MINUTES = {"fast": 14, "slow": 17, "profiles": 3, "identity": 4, "docs": 2}
DOCUMENTATION_FILES = {"AGENTS.md", "CONTRIBUTING.md", "README.md", "RELEASE_NOTES.md", "NOTICE.md"}


def expected_minutes(lane: str) -> float:
    if lane in EXPECTED_MINUTES:
        return EXPECTED_MINUTES[lane]
    for chunk in ROUTE_CHUNKS:
        if route_lane_name(chunk) == lane:
            return 4.0 * (chunk.last - chunk.first + 1)
    return 10.0


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def source_files() -> list[str]:
    if not (ROOT / ".git").exists():
        raise SystemExit("ci_local needs a git checkout: it copies the files a commit would contain")
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    return sorted({name for name in listed if name and (ROOT / name).is_file()})


def changed_files(base: str) -> list[str]:
    committed = git("diff", "--name-only", f"{base}...HEAD").split()
    working = git("diff", "--name-only", "HEAD").split()
    untracked = git("ls-files", "--others", "--exclude-standard").split()
    return sorted(set(committed) | set(working) | set(untracked))


def documentation_only(paths: list[str]) -> bool:
    return bool(paths) and all(
        path in DOCUMENTATION_FILES or (path.startswith("docs/") and path.endswith(".md")) for path in paths)


def copy_tree(files: list[str], destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)


def lane_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("LUPINE3D_")}
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def resolve(command: list[str]) -> list[str]:
    if command[0] == "make":
        return command + [f"PYTHON={sys.executable}"]
    if command[0] == "python":
        return [sys.executable] + command[1:]
    return command


def run_lane(name: str, commands: list[list[str]], files: list[str], output: Path) -> dict:
    tree = output / name
    log_path = output / f"{name}.log"
    started = time.monotonic()
    result = {"lane": name, "status": "passed", "commands": [], "log": str(log_path.relative_to(ROOT))}
    if name in CORE_LANES and not all((ROOT / path).is_dir() for path in (SAMEBOY_DIR, MGBA_DIR)):
        result.update(status="skipped", reason=f"pinned cores are not under {SAMEBOY_DIR} and {MGBA_DIR}")
        return result
    copy_tree(files, tree)
    if name in CORE_LANES:
        (tree / "build").mkdir(exist_ok=True)
        (tree / "build" / "deps").symlink_to(ROOT / "build" / "deps", target_is_directory=True)
    env = lane_environment()
    with log_path.open("w", encoding="utf-8") as log:
        for command in commands:
            command_started = time.monotonic()
            log.write(f"$ {' '.join(command)}\n")
            log.flush()
            completed = subprocess.run(resolve(command), cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT)
            seconds = round(time.monotonic() - command_started, 1)
            result["commands"].append({"command": " ".join(command), "exit": completed.returncode, "seconds": seconds})
            if completed.returncode != 0:
                result["status"] = "failed"
                break
    rom = tree / "build" / "lupine3d.gb"
    if rom.is_file():
        result["rom_sha256"] = hashlib.sha256(rom.read_bytes()).hexdigest()
    for chunk in ROUTE_CHUNKS:
        report_dir = tree / chunk.directory
        if route_lane_name(chunk) == name and report_dir.is_dir():
            destination = ROOT / chunk.directory
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(report_dir, destination)
            result["route_report"] = chunk.directory + "/report.json"
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lanes", help="comma-separated lanes (default: every CI lane; see --list)")
    parser.add_argument("--changed", action="store_true", help="choose lanes from what changed against --base")
    parser.add_argument("--base", default="origin/main", help="the comparison for --changed (default origin/main)")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 2, help="lanes at once (default: CPUs)")
    parser.add_argument("--output-dir", default="build/ci-local")
    parser.add_argument("--keep", action="store_true", help="keep the trees of lanes that passed")
    parser.add_argument("--list", action="store_true", help="print the lanes and their commands")
    parser.add_argument("--dry-run", action="store_true", help="print the lanes that would run, run nothing")
    args = parser.parse_args(argv)

    lanes = all_lanes()
    if args.list:
        for name, commands in {**lanes, **DOCS_LANE}.items():
            print(f"{name}:")
            for command in commands:
                print(f"  {' '.join(command)}")
        return 0

    if args.lanes:
        wanted = [name.strip() for name in args.lanes.split(",") if name.strip()]
        unknown = [name for name in wanted if name not in lanes and name not in DOCS_LANE]
        if unknown:
            raise SystemExit(f"unknown lanes {unknown}; see --list")
        selected = {name: {**lanes, **DOCS_LANE}[name] for name in wanted}
    elif args.changed:
        changed = changed_files(args.base)
        if not changed:
            print(f"nothing changed against {args.base}")
            return 0
        if documentation_only(changed):
            print(f"{len(changed)} documentation file(s) changed: running the docs lane")
            selected = dict(DOCS_LANE)
        else:
            print(f"{len(changed)} file(s) changed, not only documentation: running every lane")
            selected = lanes
    else:
        selected = lanes

    if args.dry_run:
        print("would run: " + ", ".join(sorted(selected, key=expected_minutes, reverse=True)))
        return 0

    output = (ROOT / args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = source_files()
    order = sorted(selected, key=expected_minutes, reverse=True)
    print(f"{len(order)} lane(s), {args.jobs} at a time, {len(files)} source files; logs in {output.relative_to(ROOT)}/")
    started = time.monotonic()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_lane, name, selected[name], files, output): name for name in order}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            detail = result.get("reason") or next(
                (f"`{c['command']}` exited {c['exit']}" for c in result["commands"] if c["exit"]), "")
            print(f"  {result['status']:>7}  {result['lane']:<12} {result.get('seconds', 0) / 60:5.1f} min  {detail}",
                  flush=True)
            if result["status"] == "passed" and not args.keep:
                shutil.rmtree(output / result["lane"], ignore_errors=True)

    roms = {r["rom_sha256"] for r in results if "rom_sha256" in r}
    summary = {
        "schema": "lupine3d.ci-local.v1",
        "source_head": git("rev-parse", "HEAD").strip(),
        "working_tree_clean": not git("status", "--porcelain").strip(),
        "minutes": round((time.monotonic() - started) / 60, 1),
        "rom_sha256": sorted(roms),
        "lanes": sorted(results, key=lambda r: r["lane"]),
    }
    failed = [r["lane"] for r in results if r["status"] == "failed"]
    skipped = [r["lane"] for r in results if r["status"] == "skipped"]
    summary["passed"] = not failed and not skipped and len(roms) <= 1
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{summary['minutes']} min wall clock; ROM {', '.join(sha[:8] for sha in sorted(roms)) or 'none'}")
    if len(roms) > 1:
        print("FAILED: the lanes built different ROMs")
    if failed:
        print(f"FAILED: {', '.join(sorted(failed))} (logs in {output.relative_to(ROOT)}/)")
    if skipped:
        print(f"INCOMPLETE: {', '.join(sorted(skipped))} skipped")
    if summary["passed"]:
        print("PASSED: every selected lane")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
