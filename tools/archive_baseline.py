#!/usr/bin/env python3
"""Preserve immutable, content-verified local evidence outside make clean's scope."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

BASELINE_COMMIT = "466bd09786d076c1e4b528f32647aa2885d201ff"
BASELINE_SHA256 = "8f0425f07220d7649ff419c9c3fb0a212c4a234b40463ab431c1f97e1b7b3cd3"
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(source, destination, *, expected_sha=BASELINE_SHA256, kind="baseline"):
    source, destination = Path(source), Path(destination)
    if digest(source / "lupine3d.gb") != expected_sha:
        raise ValueError("ROM does not match the requested baseline")
    manifest = json.loads((source / "build_manifest.json").read_text())
    if manifest["sha256"] != expected_sha:
        raise ValueError("Manifest belongs to a different ROM")
    files = [source / name for name in ("lupine3d.gb", "lupine3d.sym", "lupine3d.lst", "build_manifest.json")]
    files += sorted(path for path in source.rglob("*")
                    if path.is_file() and path.suffix in (".json", ".png", ".ppm", ".gif", ".bin", ".log")
                    and "deps" not in path.relative_to(source).parts
                    and "cache" not in path.relative_to(source).parts
                    and path not in files)
    index = dict(schema="lupine3d.baseline.v1", source_commit=BASELINE_COMMIT,
                 rom_sha256=expected_sha, files={str(p.relative_to(source)): digest(p) for p in files})
    if kind != "baseline":
        index.update(schema="lupine3d.comparison-archive.v1", kind=kind,
                     source_commit=None, based_on_commit=BASELINE_COMMIT)
    if destination.exists():
        existing = json.loads((destination / "archive.json").read_text())
        for name, sha in existing["files"].items():
            if digest(destination / name) != sha:
                raise ValueError(f"Archived evidence was changed: {name}")
        if existing != index:
            raise FileExistsError("Archive is immutable; choose a new evidence directory")
        return existing
    destination.mkdir(parents=True)
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        target.chmod(0o444)
    target = destination / "archive.json"
    target.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    target.chmod(0o444)
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "build")
    parser.add_argument("--output", type=Path, default=ROOT / ".render-baselines" / BASELINE_COMMIT)
    parser.add_argument("--expected-sha", default=BASELINE_SHA256)
    parser.add_argument("--kind", choices=("baseline", "performance"), default="baseline")
    args = parser.parse_args()
    result = archive(args.source, args.output, expected_sha=args.expected_sha, kind=args.kind)
    print(f"Preserved {len(result['files'])} files at {args.output}; ROM {result['rom_sha256']}")
