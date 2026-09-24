#!/usr/bin/env python3
"""Documentation checks for the fast lane.

- Every relative link in a Markdown file resolves to a file or directory.
- Every `make <target>` in a command (fenced block or inline code) names a
  target the Makefile defines, and every `python tools/<script>.py` names a
  script that exists. Archived documents and milestones keep their links
  checked but are exempt from the command checks: they describe the tooling
  of their day.
- `docs/guide/MEMORY_MAP.md` matches the current build manifest when one
  exists (`tools/memory_map.py --check`).

    python tools/check_docs.py [--require-build]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "build", "dist", ".git", "node_modules", "__pycache__"}
HISTORICAL = ("docs/archive/", "milestones/", "research/", "games/sable_outpost/playtests/archive/")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
INLINE = re.compile(r"`([^`\n]+)`")
MAKE = re.compile(r"(?:^|&&|;|\|)\s*(?:[A-Z0-9_]+=\S+\s+)*make\s+([^&|;\n]*)")
PYTHON = re.compile(r"(?:python3?|\.venv/bin/python)\s+(tools/[\w./-]+\.py)")
TARGET = re.compile(r"^[a-z][a-z0-9_-]*$")


def markdown_files() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return sorted(out)


def makefile_targets() -> set[str]:
    targets = set()
    for line in (ROOT / "Makefile").read_text().splitlines():
        match = re.match(r"^([A-Za-z0-9_./-]+)\s*:", line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


def strip_code(text: str) -> tuple[str, list[str]]:
    """Text without fenced blocks, and the command lines the blocks and
    inline code spans contain."""
    commands: list[str] = []
    for block in FENCE.findall(text):
        commands += block.splitlines()
    prose = FENCE.sub("", text)
    commands += INLINE.findall(prose)
    return prose, commands


def check_links(path: Path, text: str, problems: list[str]) -> None:
    for pattern in (LINK, IMAGE):
        for target in pattern.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            location = target.split("#", 1)[0]
            if not location:
                continue
            resolved = (path.parent / location).resolve()
            if not resolved.exists():
                problems.append(f"{path.relative_to(ROOT)}: broken link {target}")


def check_commands(path: Path, commands: list[str], targets: set[str], problems: list[str]) -> None:
    for line in commands:
        line = line.split("#", 1)[0]          # a shell comment is prose, not a target list
        for arguments in MAKE.findall(line):
            tokens = arguments.split()
            if any(token in ("-C", "-f") or token.startswith(("-C", "-f")) for token in tokens):
                continue                      # another project's Makefile
            for token in tokens:
                if "=" in token or not TARGET.match(token):
                    continue
                if token not in targets:
                    problems.append(f"{path.relative_to(ROOT)}: `make {token}` is not a Makefile target")
        for script in PYTHON.findall(line):
            if not (ROOT / script).is_file():
                problems.append(f"{path.relative_to(ROOT)}: {script} does not exist")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--require-build", action="store_true", help="fail when there is no build manifest to check the memory map against")
    args = parser.parse_args(argv)
    targets = makefile_targets()
    problems: list[str] = []
    files = markdown_files()
    for path in files:
        text = path.read_text(encoding="utf-8")
        prose, commands = strip_code(text)
        check_links(path, text, problems)
        relative = str(path.relative_to(ROOT))
        if not relative.startswith(HISTORICAL):
            check_commands(path, commands, targets, problems)
    manifest = ROOT / "build" / "build_manifest.json"
    if manifest.is_file():
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "memory_map.py"), "--check"],
                                capture_output=True, text=True)
        if result.returncode:
            problems.append((result.stderr or result.stdout).strip())
    elif args.require_build:
        problems.append("no build manifest: the memory map cannot be checked")
    else:
        print("no build manifest; memory map check skipped")
    for problem in problems:
        print(problem)
    print(f"{len(files)} Markdown files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
