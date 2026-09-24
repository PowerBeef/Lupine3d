#!/usr/bin/env python3
"""Documentation checks for the fast lane.

- Every relative link in a Markdown file resolves to a file or directory.
- Every `make <target>` in a command (fenced block or inline code) names a
  target the Makefile defines, and every `python tools/<script>.py` names a
  script that exists. Archived documents and milestones keep their links
  checked but are exempt from the command checks: they describe the tooling
  of their day.
- `docs/reference/memory-map.md` matches the current build manifest when one
  exists (`tools/memory_map.py --check`).
- A link's `#anchor` names a heading of the page it points at (GitHub's
  slug rules).
- Every `lupine <command>` a page runs is a real subcommand, and
  `docs/reference/cli.md` documents every subcommand.
- `docs/reference/build-flags.md` has a row for every `LUPINE3D_*` variable
  the code reads, and names no variable the code does not.
- `docs/reference/game-manifest.md` lists exactly the keys the game loader
  accepts for each object (`game.KEYS`), and `docs/reference/limits.md`
  exactly the limits table (`limits.LIMITS`); a number written
  `20<!-- limit:levels -->` is that limit's maximum.
- `docs/reference/palettes.md` marks as *theme* exactly the palettes a theme
  sets.
- A backticked repository path in a current page exists, and a backticked
  `file.py:symbol` names something that file defines.

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


def heading_slugs(text: str) -> set[str]:
    """GitHub's anchors for a page's headings: lower-cased, punctuation
    dropped except hyphens and underscores, spaces to hyphens, repeats
    numbered."""
    slugs: set[str] = set()
    counts: dict[str, int] = {}
    for line in FENCE.sub("", text).splitlines():
        match = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1))
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    return slugs


def check_anchors(path: Path, text: str, problems: list[str]) -> None:
    for pattern in (LINK,):
        for target in pattern.findall(text):
            if re.match(r"^[a-z]+:", target) or "#" not in target:
                continue
            location, anchor = target.split("#", 1)
            page = (path.parent / location).resolve() if location else path
            if page.suffix != ".md" or not page.is_file():
                continue
            if anchor not in heading_slugs(page.read_text(encoding="utf-8")):
                problems.append(f"{path.relative_to(ROOT)}: link {target} names no heading of {page.relative_to(ROOT)}")


LUPINE = re.compile(r"lupine(?:\.py)?\s+([a-z][a-z-]*)")


def lupine_commands() -> set[str]:
    sys.path.insert(0, str(ROOT / "tools"))
    import lupine
    parser = lupine.build_parser()
    action = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    return set(action.choices)


def check_lupine(path: Path, commands: list[str], known: set[str], problems: list[str]) -> None:
    for line in commands:
        for name in LUPINE.findall(line.split("#", 1)[0]):
            if name not in known:
                problems.append(f"{path.relative_to(ROOT)}: `lupine {name}` is not a subcommand")


def check_cli_reference(known: set[str], problems: list[str]) -> None:
    page = ROOT / "docs" / "reference" / "cli.md"
    documented = set(re.findall(r"^###\s+`lupine ([a-z-]+)`", page.read_text(encoding="utf-8"), re.M))
    for name in sorted(known - documented):
        problems.append(f"docs/reference/cli.md: `lupine {name}` has no section")
    for name in sorted(documented - known):
        problems.append(f"docs/reference/cli.md: documents `lupine {name}`, which is not a subcommand")


FLAG = re.compile(r"LUPINE3D_[A-Z0-9_]+")


def code_flags() -> set[str]:
    """Every LUPINE3D_* name the code reads: spelled out, or built from the
    rendering flag table (`"LUPINE3D_" + flag`)."""
    names: set[str] = set()
    for pattern in ("tools/*.py", "tools/*.c", "tools/lupine3d_v4/*.py", "research/*.py"):
        for source in ROOT.glob(pattern):
            names |= set(FLAG.findall(source.read_text(encoding="utf-8", errors="replace")))
    sys.path.insert(0, str(ROOT / "tools"))
    from lupine3d_v4.configuration import FLAGS
    names |= {"LUPINE3D_" + flag for flag in FLAGS.values()}
    return names


def check_build_flags(problems: list[str], code: set[str] | None = None) -> None:
    page = ROOT / "docs" / "reference" / "build-flags.md"
    rows = set(re.findall(r"^\|\s*`(LUPINE3D_[A-Z0-9_]+)`", page.read_text(encoding="utf-8"), re.M))
    rows |= {name for line in page.read_text(encoding="utf-8").splitlines() if line.startswith("|")
             for name in re.findall(r"`(LUPINE3D_[A-Z0-9_]+)`", line.split("|")[1])}
    code = code_flags() if code is None else code
    for name in sorted(code - rows):
        problems.append(f"docs/reference/build-flags.md: no row for {name}")
    for name in sorted(rows - code):
        problems.append(f"docs/reference/build-flags.md: documents {name}, which no code reads")


def manifest_sections(text: str) -> dict[str, set[str]]:
    """`### \`name\`` sections of the manifest reference and the keys their
    tables list in the first column."""
    sections: dict[str, set[str]] = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^###\s+`([a-z_.]+)`\s*$", line)
        if heading:
            current = sections.setdefault(heading.group(1), set())
            continue
        row = re.match(r"^\|\s*`([$a-z_0-9]+)`\s*\|", line)
        if current is not None and row:
            current.add(row.group(1))
    return sections


def check_manifest_reference(problems: list[str], text: str | None = None) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from lupine3d_v4.game import KEYS
    page = ROOT / "docs" / "reference" / "game-manifest.md"
    sections = manifest_sections(page.read_text(encoding="utf-8") if text is None else text)
    for name, (allowed, _required) in KEYS.items():
        if name.startswith(("screen", "song", "sound")):
            continue                            # those files have their own pages
        documented = sections.get(name)
        if documented is None:
            problems.append(f"docs/reference/game-manifest.md: no section for `{name}`")
        elif documented != set(allowed):
            problems.append(f"docs/reference/game-manifest.md: `{name}` lists {sorted(documented)}, "
                            f"the loader accepts {sorted(allowed)}")


LIMIT_MARK = re.compile(r"(\d[\d,]*)\s*<!--\s*limit:([a-z_]+)\s*-->")


def check_limits(files: list[Path], problems: list[str]) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from lupine3d_v4.limits import LIMITS
    for path in files:
        for number, name in LIMIT_MARK.findall(path.read_text(encoding="utf-8")):
            if name not in LIMITS:
                problems.append(f"{path.relative_to(ROOT)}: limit:{name} is not a limit")
            elif int(number.replace(",", "")) != LIMITS[name].maximum:
                problems.append(f"{path.relative_to(ROOT)}: says {number} for limit:{name}, "
                                f"which is {LIMITS[name].maximum}")
    page = ROOT / "docs" / "reference" / "limits.md"
    rows = {name: (int(low), int(high)) for name, low, high in
            re.findall(r"^\|\s*`([a-z_]+)`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", page.read_text(encoding="utf-8"), re.M)}
    table = {name: (rule.minimum, rule.maximum) for name, rule in LIMITS.items()}
    if rows != table:
        problems.append(f"docs/reference/limits.md: the table differs from limits.py: "
                        f"{sorted(set(rows.items()) ^ set(table.items()))}")


def check_palette_roles(problems: list[str], text: str | None = None) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from lupine3d_v4.game import ACTOR_PALETTE_SLOTS
    if text is None:
        text = (ROOT / "docs" / "reference" / "palettes.md").read_text(encoding="utf-8")
    bg = {int(n) for n, rest in re.findall(r"^\|\s*(\d)\s*\|(.*)$", text.split("## Object palettes")[0], re.M)
          if "*theme*" in rest}
    obj = {int(n) for n, rest in re.findall(r"^\|\s*(\d)\s*\|(.*)$", text.split("## Object palettes")[1], re.M)
           if "*theme*" in rest}
    if bg != {0, 2, 3, 4, 5, 6}:
        problems.append(f"docs/reference/palettes.md: BG palettes marked *theme* are {sorted(bg)}; "
                        "a theme sets BG 0 and 2-6")
    if obj != set(ACTOR_PALETTE_SLOTS):
        problems.append(f"docs/reference/palettes.md: OBJ palettes marked *theme* are {sorted(obj)}; "
                        f"a theme sets OBJ {sorted(ACTOR_PALETTE_SLOTS)}")


# The games the tutorials and how-to guides make, by the names they give them.
EXAMPLES = ("games/my_game", "games/night_shift")
REPO_PATH = re.compile(r"^(?:tools|tests|games|docs|research|milestones|assets|\.github)/[\w./-]*[\w/]$")
SYMBOL_REF = re.compile(r"^((?:tools|tests|research)/[\w./-]+\.py):([A-Za-z_][\w.]*)$")


def check_code_references(path: Path, text: str, problems: list[str]) -> None:
    """Backticked repository paths exist; `file.py:symbol` names a symbol the file defines."""
    for token in INLINE.findall(FENCE.sub("", text)):
        token = token.strip()
        symbol = SYMBOL_REF.match(token)
        if symbol:
            source = ROOT / symbol.group(1)
            name = symbol.group(2).split(".")[-1]
            if not source.is_file():
                problems.append(f"{path.relative_to(ROOT)}: `{token}`: {symbol.group(1)} does not exist")
            elif not re.search(rf"\b{re.escape(name)}\b", source.read_text(encoding="utf-8")):
                problems.append(f"{path.relative_to(ROOT)}: `{token}`: {symbol.group(1)} has no {name}")
            continue
        if not REPO_PATH.match(token) or any(c in token for c in "<>*…{}") or token.startswith(EXAMPLES):
            continue
        if not (ROOT / token).exists():
            problems.append(f"{path.relative_to(ROOT)}: `{token}` does not exist")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--require-build", action="store_true", help="fail when there is no build manifest to check the memory map against")
    args = parser.parse_args(argv)
    targets = makefile_targets()
    problems: list[str] = []
    files = markdown_files()
    known = lupine_commands()
    for path in files:
        text = path.read_text(encoding="utf-8")
        prose, commands = strip_code(text)
        check_links(path, text, problems)
        relative = str(path.relative_to(ROOT))
        if not relative.startswith(HISTORICAL) and relative != "RELEASE_NOTES.md":
            check_commands(path, commands, targets, problems)
            check_anchors(path, text, problems)
            check_lupine(path, commands, known, problems)
            check_code_references(path, text, problems)
    check_cli_reference(known, problems)
    check_build_flags(problems)
    check_manifest_reference(problems)
    check_limits(files, problems)
    check_palette_roles(problems)
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
