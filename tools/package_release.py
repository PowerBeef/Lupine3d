#!/usr/bin/env python3
"""Create and clean-room verify the Lupine 3D release bundle.

The packager intentionally performs the release gates twice:

1. It rebuilds/tests/verifies the working tree and optionally regenerates previews.
2. It stages an allow-listed source tree, rebuilds that clean copy, writes a
   deterministic ZIP, extracts the ZIP into another empty directory, rebuilds
   it again, runs the full test suite, and compares the ROM byte-for-byte.

Only after those checks pass are the user-facing artifacts and SHA-256 manifest
published to the requested output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
PROJECT_SLUG = "Lupine3D"
ARCHIVE_ROOT = f"{PROJECT_SLUG}_v{VERSION}"

TOP_LEVEL_FILES = (
    ".gitignore",
    "LICENSE",
    "Makefile",
    "NOTICE.md",
    "README.md",
    "RELEASE_NOTES.md",
    "VERSION",
    "requirements.txt",
)
TOP_LEVEL_DIRS = ("assets", "docs", "levels", "milestones", "playtests", "research", "tests", "tools")
BUILD_FILES = (
    "build_manifest.json",
    "harness_action.png",
    "harness_action_v060.png",
    "lupine3d.gb",
    "lupine3d.lst",
    "lupine3d.sym",
    "lupine3d_preview.gif",
    "lupine3d_preview_4x.png",
    "playtest/coherence_tour/contact_sheet.png",
    "playtest/coherence_tour/playtest.gif",
    "playtest/coherence_tour/report.json",
    "playtest/living_world/contact_sheet.png",
    "playtest/living_world/playtest.gif",
    "playtest/living_world/report.json",
    "verification_report.json",
)
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", "dist"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], cwd: Path, *, capture: bool = False, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    print(f"+ ({cwd}) {' '.join(command)}", flush=True)
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=timeout,
    )
    if capture:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {' '.join(command)}"
        )
    return result


def ensure_required_outputs(root: Path) -> None:
    required = [root / "build" / name for name in BUILD_FILES]
    required.extend(
        [
            root / "research" / "results" / "geometry_v2_results.json",
            root / "research" / "results" / "geometry_v2_accuracy.csv",
            root / "research" / "results" / "geometry_v2_comparison.png",
            root / "research" / "results" / "rendering_v3_results.json",
            root / "research" / "results" / "rendering_v3_accuracy.csv",
            root / "research" / "results" / "rendering_v3_before_after.png",
            root / "research" / "results" / "tile_atlas_v4.json",
            root / "research" / "results" / "tile_atlas_pareto_v5.json",
            root / "research" / "results" / "tile_atlas_entity_80_v6.json",
            root / "research" / "results" / "tail_failures_v4.json",
            root / "research" / "results" / "tail_failures_v4.csv",
            root / "research" / "results" / "tail_failures_v4.png",
        ]
    )
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("missing release outputs: " + ", ".join(missing))


def validate_verification_report(root: Path) -> dict[str, object]:
    report_path = root / "build" / "verification_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        failed = [] if not isinstance(checks, dict) else [name for name, value in checks.items() if not value]
        raise RuntimeError(f"verification report contains failed gates: {failed}")
    if report.get("physical_hardware_tested") is not False:
        raise RuntimeError("release report must preserve the explicit pending hardware-test status")
    if report.get("version") != VERSION:
        raise RuntimeError("verification report version does not match VERSION")
    return report


def run_working_tree_gates(*, regenerate_previews: bool) -> dict[str, object]:
    python = sys.executable
    run([python, "tools/build_rom.py"], ROOT)
    run([python, "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT)
    run([python, "research/geometry_v2_lab.py"], ROOT)
    run([python, "research/rendering_v3_lab.py"], ROOT)
    run([python, "tools/playtest.py"], ROOT)
    run([
        python, "tools/playtest.py", "--scenario", "playtests/living_world.json",
        "--output-dir", "build/playtest/living_world",
    ], ROOT)
    run([python, "tools/release_check.py"], ROOT)
    if regenerate_previews:
        run([python, "tools/make_preview.py"], ROOT)
    ensure_required_outputs(ROOT)
    return validate_verification_report(ROOT)


def include_path(path: Path) -> bool:
    if any(part in IGNORED_PARTS for part in path.parts):
        return False
    if path.name in IGNORED_SUFFIXES or path.suffix in {".pyc", ".pyo"}:
        return False
    return True


def iter_source_files() -> Iterable[tuple[Path, Path]]:
    for name in TOP_LEVEL_FILES:
        source = ROOT / name
        if not source.is_file():
            raise RuntimeError(f"missing source-release file: {name}")
        yield source, Path(name)

    for dirname in TOP_LEVEL_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            raise RuntimeError(f"missing source-release directory: {dirname}")
        for source in sorted(base.rglob("*")):
            relative = source.relative_to(ROOT)
            if include_path(relative) and source.is_file() and not source.is_symlink():
                yield source, relative

    for name in BUILD_FILES:
        source = ROOT / "build" / name
        if not source.is_file():
            raise RuntimeError(f"missing generated release file: build/{name}")
        yield source, Path("build") / name


def stage_source_tree(stage_root: Path) -> None:
    for source, relative in iter_source_files():
        destination = stage_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_and_compare(
    root: Path,
    expected_rom: bytes,
    *,
    run_tests: bool,
) -> dict[str, object]:
    python = sys.executable
    run([python, "tools/build_rom.py"], root)
    test_result: subprocess.CompletedProcess[str] | None = None
    if run_tests:
        test_result = run(
            [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
            root,
            capture=True,
        )
    rebuilt_path = root / "build" / "lupine3d.gb"
    rebuilt = rebuilt_path.read_bytes()
    exact = rebuilt == expected_rom
    if not exact:
        raise RuntimeError(
            "clean-room ROM mismatch: "
            f"expected {sha256_bytes(expected_rom)}, got {sha256_bytes(rebuilt)}"
        )
    return {
        "passed": True,
        "rom_exact_match": True,
        "rom_sha256": sha256_bytes(rebuilt),
        "rom_bytes": len(rebuilt),
        "tests_run": bool(run_tests),
        "test_process_exit_code": None if test_result is None else test_result.returncode,
    }


def file_manifest(root: Path, *, exclude: set[Path] | None = None) -> list[dict[str, object]]:
    excluded = exclude or set()
    entries: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if relative in excluded:
            continue
        entries.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_deterministic_zip(source_root: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as bundle:
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            relative = Path(ARCHIVE_ROOT) / source.relative_to(source_root)
            info = zipfile.ZipInfo(relative.as_posix(), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            executable = bool(source.stat().st_mode & 0o111)
            info.external_attr = ((0o100755 if executable else 0o100644) << 16)
            info.flag_bits |= 0x800  # UTF-8 names
            bundle.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def copy_artifact(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def package(
    output_dir: Path,
    *,
    regenerate_previews: bool = False,
    reuse_verified_working_tree: bool = False,
) -> list[Path]:
    if reuse_verified_working_tree:
        ensure_required_outputs(ROOT)
        report = validate_verification_report(ROOT)
        print("+ reusing current verified build/research/preview outputs", flush=True)
    else:
        report = run_working_tree_gates(regenerate_previews=regenerate_previews)
    expected_rom = (ROOT / "build" / "lupine3d.gb").read_bytes()
    expected_sha = sha256_bytes(expected_rom)
    if report["rom"]["sha256"] != expected_sha:  # type: ignore[index]
        raise RuntimeError("working-tree ROM and verification report SHA-256 disagree")

    output_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "rom": f"{PROJECT_SLUG}_v{VERSION}.gb",
        "archive": f"{PROJECT_SLUG}_v{VERSION}_complete.zip",
        "preview_png": f"{PROJECT_SLUG}_v{VERSION}_preview.png",
        "preview_gif": f"{PROJECT_SLUG}_v{VERSION}_preview.gif",
        "playtest_contact_sheet": f"{PROJECT_SLUG}_v{VERSION}_playtest.png",
        "playtest_gif": f"{PROJECT_SLUG}_v{VERSION}_playtest.gif",
        "playtest_report": f"{PROJECT_SLUG}_v{VERSION}_playtest_report.json",
        "living_world_contact_sheet": f"{PROJECT_SLUG}_v{VERSION}_living_world.png",
        "living_world_gif": f"{PROJECT_SLUG}_v{VERSION}_living_world.gif",
        "living_world_report": f"{PROJECT_SLUG}_v{VERSION}_living_world_report.json",
        "rendering_research": f"{PROJECT_SLUG}_v{VERSION}_rendering_research.json",
        "verification": f"{PROJECT_SLUG}_v{VERSION}_verification_report.json",
        "renderer_design": f"{PROJECT_SLUG}_v{VERSION}_LIVING_WORLD.md",
        "development_guide": f"{PROJECT_SLUG}_v{VERSION}_DEVELOPMENT.md",
        "clean_room": f"{PROJECT_SLUG}_v{VERSION}_clean_room_verification.json",
        "manifest": f"{PROJECT_SLUG}_v{VERSION}_release_manifest.json",
        "checksums": f"{PROJECT_SLUG}_v{VERSION}_SHA256SUMS.txt",
    }
    for name in names.values():
        destination = output_dir / name
        if destination.exists():
            destination.unlink()

    with tempfile.TemporaryDirectory(prefix="lupine3d-release-") as temporary:
        temp = Path(temporary)
        stage_root = temp / "stage" / ARCHIVE_ROOT
        stage_root.mkdir(parents=True)
        stage_source_tree(stage_root)

        staged_check = build_and_compare(stage_root, expected_rom, run_tests=False)
        internal_release_manifest = {
            "project": "Lupine 3D",
            "version": VERSION,
            "archive_root": ARCHIVE_ROOT,
            "rom": {
                "path": "build/lupine3d.gb",
                "bytes": len(expected_rom),
                "sha256": expected_sha,
            },
            "working_tree_verification": {
                "all_checks_passed": True,
                "automated_tests": report["automated_tests"],
                "physical_hardware_tested": False,
            },
            "staged_clean_room_rebuild": staged_check,
            "post_archive_extract_rebuild": "performed by tools/package_release.py before publication",
        }
        write_json(stage_root / "build" / "release_manifest.json", internal_release_manifest)

        source_manifest_path = stage_root / "SOURCE_MANIFEST.json"
        source_manifest = {
            "project": "Lupine 3D",
            "version": VERSION,
            "archive_root": ARCHIVE_ROOT,
            "files": file_manifest(stage_root, exclude={Path("SOURCE_MANIFEST.json")}),
        }
        write_json(source_manifest_path, source_manifest)

        archive_path = output_dir / names["archive"]
        write_deterministic_zip(stage_root, archive_path)

        extracted_parent = temp / "extracted"
        extracted_parent.mkdir()
        with zipfile.ZipFile(archive_path, "r") as bundle:
            bundle.extractall(extracted_parent)
        extracted_root = extracted_parent / ARCHIVE_ROOT
        if not extracted_root.is_dir():
            raise RuntimeError("release archive did not contain the expected top-level directory")
        extracted_check = build_and_compare(extracted_root, expected_rom, run_tests=True)

    clean_room_evidence = {
        "project": "Lupine 3D",
        "version": VERSION,
        "archive": names["archive"],
        "archive_sha256": sha256_file(output_dir / names["archive"]),
        "expected_rom_sha256": expected_sha,
        "staged_source_rebuild": staged_check,
        "post_archive_extract_rebuild_and_tests": extracted_check,
        "result": "pass",
        "physical_hardware_tested": False,
    }
    clean_room_build_path = ROOT / "build" / "clean_room_verification.json"
    write_json(clean_room_build_path, clean_room_evidence)

    artifact_sources = {
        "rom": ROOT / "build" / "lupine3d.gb",
        "preview_png": ROOT / "build" / "lupine3d_preview_4x.png",
        "preview_gif": ROOT / "build" / "lupine3d_preview.gif",
        "playtest_contact_sheet": ROOT / "build" / "playtest" / "coherence_tour" / "contact_sheet.png",
        "playtest_gif": ROOT / "build" / "playtest" / "coherence_tour" / "playtest.gif",
        "playtest_report": ROOT / "build" / "playtest" / "coherence_tour" / "report.json",
        "living_world_contact_sheet": ROOT / "build" / "playtest" / "living_world" / "contact_sheet.png",
        "living_world_gif": ROOT / "build" / "playtest" / "living_world" / "playtest.gif",
        "living_world_report": ROOT / "build" / "playtest" / "living_world" / "report.json",
        "rendering_research": ROOT / "research" / "results" / "rendering_v3_results.json",
        "verification": ROOT / "build" / "verification_report.json",
        "renderer_design": ROOT / "docs" / "LIVING_WORLD_V6.md",
        "development_guide": ROOT / "docs" / "DEVELOPMENT.md",
        "clean_room": clean_room_build_path,
    }
    for key, source in artifact_sources.items():
        copy_artifact(source, output_dir / names[key])

    artifact_paths = [
        output_dir / names["rom"],
        output_dir / names["archive"],
        output_dir / names["preview_png"],
        output_dir / names["preview_gif"],
        output_dir / names["playtest_contact_sheet"],
        output_dir / names["playtest_gif"],
        output_dir / names["playtest_report"],
        output_dir / names["living_world_contact_sheet"],
        output_dir / names["living_world_gif"],
        output_dir / names["living_world_report"],
        output_dir / names["rendering_research"],
        output_dir / names["verification"],
        output_dir / names["renderer_design"],
        output_dir / names["development_guide"],
        output_dir / names["clean_room"],
    ]
    external_manifest = {
        "project": "Lupine 3D",
        "version": VERSION,
        "publication_status": "software release complete; original-hardware certification pending",
        "physical_hardware_tested": False,
        "rom": {
            "bytes": len(expected_rom),
            "sha256": expected_sha,
        },
        "working_tree_gates": {
            "verification_checks": len(report["checks"]),  # type: ignore[arg-type]
            "all_checks_passed": True,
            "automated_tests": report["automated_tests"],
        },
        "clean_room": {
            "staged_rebuild": staged_check,
            "post_archive_extract_rebuild_and_tests": extracted_check,
            "archive_rom_exact_match": True,
        },
        "artifacts": [
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in artifact_paths
        ],
    }
    manifest_path = output_dir / names["manifest"]
    write_json(manifest_path, external_manifest)
    artifact_paths.append(manifest_path)

    checksums_path = output_dir / names["checksums"]
    checksums_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in sorted(artifact_paths)),
        encoding="utf-8",
    )
    artifact_paths.append(checksums_path)

    # Keep the machine-readable packaging result with the normal build evidence.
    write_json(ROOT / "build" / "release_manifest.json", external_manifest)

    print("\nRelease artifacts:")
    for path in artifact_paths:
        print(f"  {path} ({path.stat().st_size} bytes, sha256={sha256_file(path)})")
    return artifact_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="directory for named release artifacts (default: %(default)s)",
    )
    parser.add_argument(
        "--reuse-verified-working-tree",
        action="store_true",
        help="skip regenerating working-tree gates; clean-room rebuild/tests still run",
    )
    parser.add_argument(
        "--regenerate-previews",
        action="store_true",
        help="rerun the comparatively expensive animated preview generator",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    package(
        output_dir,
        regenerate_previews=args.regenerate_previews,
        reuse_verified_working_tree=args.reuse_verified_working_tree,
    )


if __name__ == "__main__":
    main()
