#!/usr/bin/env python3
"""Golden-image snapshots for emitted-ROM captures: check, diff, accept.

A snapshot is a 160×144 RGB image the host harness rendered from the machine's
own VRAM, OAM and palettes, stored beside a manifest that binds it to the ROM
and configuration it was accepted on. Producers (the driven playtests, the
Sable checks, the frozen witness scenes, the controller route) hand every
capture to a `Suite`; the suite compares it with the golden of the same name,
writes an `actual`, an `expected` copy and a `diff` image, and a JSON and HTML
report a reviewer can read without the repository.

Modes: `check` fails the producer when any scene changed, is new, or is
missing; `record` writes the same evidence and never fails. Accepting a change
is deliberate and explained: `snapshot accept --suite … --scene … --note …`
copies the actual image over the golden and records who, when, which ROM and
why. Nothing in CI accepts.

Engine invariants are not snapshots. Geometry and compositor model equality,
publication safety, the bank contract and independent-core agreement remain
hard gates in their own tools; a snapshot only says what the frame looked like.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

SCHEMA = "lupine3d.snapshots.v1"
SNAPSHOT_ROOT = ROOT / "snapshots"
FAST_SUITES = ("tour", "world", "art", "sable", "witnesses")
ALL_SUITES = FAST_SUITES + ("route",)
MODES = ("check", "record")


def rgb_sha256(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def profile_name() -> str:
    """The display/art profile a golden belongs to; flags never enter it."""
    import build_rom as br
    config = br.RENDER_CONFIG
    name = f"{config['display']}-{config['art']}"
    if not config.get("art_animation", True):
        name += "-static"
    if config.get("textured_walls"):
        name += "-textured"
    return name


def build_identity(build_dir: Path | None = None) -> tuple[str, str]:
    """ROM SHA-256 and configuration id of a build: the default build, or
    the one whose manifest sits in `build_dir` (a profile built elsewhere)."""
    import build_rom as br
    manifest_path = (build_dir or br.BUILD) / "build_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        return manifest["sha256"], manifest["configuration_id"]
    rom, _, manifest = br.make_rom()
    return hashlib.sha256(rom).hexdigest(), manifest["configuration_id"]


def compare(expected: Image.Image | None, actual: Image.Image, *, hud_row: int | None = None) -> dict[str, Any]:
    """Exact RGB comparison with the reviewer's numbers attached."""
    actual = actual.convert("RGB")
    record: dict[str, Any] = {"actual_sha256": rgb_sha256(actual), "changed_pixels": 0, "bbox": None,
                              "world_pixels": 0, "hud_pixels": 0}
    if expected is None:
        record.update(status="new", expected_sha256=None)
        return record
    expected = expected.convert("RGB")
    record["expected_sha256"] = rgb_sha256(expected)
    if expected.size != actual.size:
        record.update(status="changed", changed_pixels=actual.size[0] * actual.size[1],
                      bbox=[0, 0, actual.size[0], actual.size[1]], size_mismatch=True)
        return record
    if expected.tobytes() == actual.tobytes():
        record["status"] = "match"
        return record
    width, height = actual.size
    ea, aa = expected.tobytes(), actual.tobytes()
    x0 = y0 = 1 << 30
    x1 = y1 = -1
    changed = world = hud = 0
    for y in range(height):
        row = y * width * 3
        for x in range(width):
            offset = row + x * 3
            if ea[offset:offset + 3] != aa[offset:offset + 3]:
                changed += 1
                if hud_row is not None and y >= hud_row:
                    hud += 1
                else:
                    world += 1
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    record.update(status="changed", changed_pixels=changed, bbox=[x0, y0, x1 + 1, y1 + 1],
                  world_pixels=world, hud_pixels=hud)
    return record


def diff_image(expected: Image.Image | None, actual: Image.Image) -> Image.Image:
    """Changed pixels in red over the dimmed actual; a new scene is all actual."""
    actual = actual.convert("RGB")
    if expected is None:
        return actual.copy()
    expected = expected.convert("RGB")
    out = Image.eval(actual, lambda value: value // 3)
    if expected.size != actual.size:
        return out
    pixels = out.load()
    ea, aa = expected.tobytes(), actual.tobytes()
    width, height = actual.size
    for y in range(height):
        row = y * width * 3
        for x in range(width):
            offset = row + x * 3
            if ea[offset:offset + 3] != aa[offset:offset + 3]:
                pixels[x, y] = (255, 40, 40)
    return out


class Suite:
    """One producer's captures against one golden directory.

    `observe(scene, image)` compares and records; `finish()` writes the
    evidence and, in `check` mode, raises `SystemExit` naming every scene
    that is not an exact match.
    """

    def __init__(self, suite: str, *, mode: str = "check", profile: str | None = None,
                 root: Path | None = None, output_dir: Path | None = None,
                 rom_sha256: str | None = None, configuration_id: str | None = None,
                 hud_row: int | None = None) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown snapshot mode: {mode}")
        self.suite, self.mode = suite, mode
        self.profile = profile or profile_name()
        self.root = root or SNAPSHOT_ROOT
        self.golden_dir = self.root / self.profile / suite
        self.manifest_path = self.golden_dir / "manifest.json"
        self.manifest = self.load_manifest(self.manifest_path)
        if output_dir is None:
            import build_rom as br
            output_dir = br.BUILD / "snapshots" / self.profile / suite
        self.output_dir = output_dir
        if rom_sha256 is None or configuration_id is None:
            rom_sha256, configuration_id = build_identity()
        self.rom_sha256, self.configuration_id = rom_sha256, configuration_id
        if hud_row is None:
            try:
                import build_rom as br
                hud_row = br.VIEW_HEIGHT
            except Exception:  # pragma: no cover - synthetic test images
                hud_row = None
        self.hud_row = hud_row
        self.scenes: dict[str, dict[str, Any]] = {}
        self.images: list[tuple[str, Image.Image]] = []
        for name in ("actual", "expected", "diff"):
            (self.output_dir / name).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_manifest(path: Path) -> dict[str, Any]:
        if path.is_file():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("schema") != SCHEMA:
                raise ValueError(f"{path}: unexpected schema {manifest.get('schema')!r}")
            return manifest
        return {"schema": SCHEMA, "scenes": {}}

    def golden(self, scene: str) -> Image.Image | None:
        path = self.golden_dir / f"{scene}.png"
        entry = self.manifest["scenes"].get(scene)
        if entry is None or not path.is_file():
            return None
        image = Image.open(path).convert("RGB")
        if rgb_sha256(image) != entry["rgb_sha256"]:
            raise AssertionError(f"golden {path} does not match its manifest entry")
        return image

    def observe(self, scene: str, image: Image.Image) -> dict[str, Any]:
        if scene in self.scenes:
            raise ValueError(f"scene observed twice: {scene}")
        actual = image.convert("RGB")
        expected = self.golden(scene)
        record = compare(expected, actual, hud_row=self.hud_row)
        record["scene"] = scene
        entry = self.manifest["scenes"].get(scene)
        if entry is not None:
            record["accepted"] = {key: entry.get(key) for key in ("rom_sha256", "accepted_at", "note")}
        actual.save(self.output_dir / "actual" / f"{scene}.png")
        if expected is not None:
            expected.save(self.output_dir / "expected" / f"{scene}.png")
        diff_image(expected, actual).save(self.output_dir / "diff" / f"{scene}.png")
        self.scenes[scene] = record
        self.images.append((scene, actual))
        return record

    def report(self) -> dict[str, Any]:
        missing = sorted(set(self.manifest["scenes"]) - set(self.scenes))
        scenes = dict(self.scenes)
        for scene in missing:
            scenes[scene] = {"scene": scene, "status": "missing", "changed_pixels": 0, "bbox": None,
                             "expected_sha256": self.manifest["scenes"][scene]["rgb_sha256"], "actual_sha256": None}
        counts = {status: sum(1 for r in scenes.values() if r["status"] == status)
                  for status in ("match", "changed", "new", "missing")}
        return {"schema": SCHEMA, "suite": self.suite, "profile": self.profile, "mode": self.mode,
                "rom_sha256": self.rom_sha256, "configuration_id": self.configuration_id,
                "golden_dir": str(self.golden_dir.relative_to(ROOT)) if self.golden_dir.is_relative_to(ROOT) else str(self.golden_dir),
                "counts": counts, "passed": counts["match"] == len(scenes) and bool(scenes),
                "scenes": [scenes[name] for name in sorted(scenes)]}

    def finish(self) -> dict[str, Any]:
        report = self.report()
        (self.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (self.output_dir / "report.html").write_text(render_html(report), encoding="utf-8")
        if self.images:
            from playtest import make_contact_sheet
            make_contact_sheet(self.images, self.output_dir / "contact_sheet.png")
        if self.mode == "check" and not report["passed"]:
            problems = ", ".join(f"{r['scene']} ({r['status']}"
                                 + (f", {r['changed_pixels']} px" if r["status"] == "changed" else "") + ")"
                                 for r in report["scenes"] if r["status"] != "match")
            raise SystemExit(
                f"snapshot suite '{self.suite}' ({self.profile}) differs from its goldens: {problems}. "
                f"Review {self.output_dir / 'report.html'}; accept a deliberate change with "
                f"`python tools/snapshot.py accept --suite {self.suite} --scene <name> --note '<why>'`.")
        return report


def render_html(report: dict[str, Any]) -> str:
    """One static page: side-by-side expected / actual / diff at 2×, no scripts."""
    rows = []
    for record in report["scenes"]:
        scene = html.escape(record["scene"])
        status = record["status"]
        detail = ""
        if status == "changed":
            detail = f"{record['changed_pixels']} px changed, bbox {record['bbox']}"
            if record.get("world_pixels") is not None:
                detail += f" (world {record['world_pixels']}, HUD {record['hud_pixels']})"
        elif status == "new":
            detail = "no golden yet"
        elif status == "missing":
            detail = "golden exists but the producer no longer captures it"
        accepted = record.get("accepted") or {}
        note = html.escape(str(accepted.get("note") or ""))
        cells = []
        for column in ("expected", "actual", "diff"):
            exists = not (column == "expected" and status == "new") and status != "missing"
            cells.append(f'<td><img src="{column}/{scene}.png" alt="{column}"></td>' if exists else "<td>—</td>")
        rows.append(f'<tr class="{status}"><th>{scene}<br><span class="status">{status}</span>'
                    f'<br><small>{html.escape(detail)}</small>'
                    + (f'<br><small class="note">accepted: {note}</small>' if note else "") + "</th>"
                    + "".join(cells) + "</tr>")
    counts = ", ".join(f"{k} {v}" for k, v in report["counts"].items())
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Snapshots: {html.escape(report['suite'])} ({html.escape(report['profile'])})</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0c0f15;color:#e6e6e6;margin:24px}}
table{{border-collapse:collapse}} th,td{{padding:8px;vertical-align:top;text-align:left;border-bottom:1px solid #333}}
img{{width:320px;height:288px;image-rendering:pixelated;image-rendering:crisp-edges;background:#000}}
tr.changed th{{color:#ffb050}} tr.new th{{color:#7fc8ff}} tr.missing th{{color:#ff6060}} tr.match th{{color:#9ad48a}}
.status{{font-weight:bold}} .note{{color:#bbb}} code{{color:#e5b760}}
</style></head><body>
<h1>Snapshot suite <code>{html.escape(report['suite'])}</code> — profile <code>{html.escape(report['profile'])}</code></h1>
<p>ROM <code>{html.escape(report['rom_sha256'])}</code> · configuration <code>{html.escape(str(report['configuration_id']))}</code> · mode {html.escape(report['mode'])} · {html.escape(counts)} · <b>{'PASS' if report['passed'] else 'DIFFERS'}</b></p>
<p>Columns: expected golden, actual capture, diff (changed pixels in red over the dimmed actual). Images are 2× nearest-neighbour.</p>
<table><thead><tr><th>Scene</th><th>Expected</th><th>Actual</th><th>Diff</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table></body></html>
"""


def git_identity() -> str:
    try:
        return subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or os.environ.get("USER", "unknown")
    except OSError:  # pragma: no cover
        return os.environ.get("USER", "unknown")


def accept(suite: str, scenes: list[str] | None, note: str, *, profile: str | None = None,
           root: Path | None = None, output_dir: Path | None = None, accepted_by: str | None = None) -> dict[str, Any]:
    """Promote actual captures from the last run of a suite to its goldens."""
    if not note or not note.strip():
        raise SystemExit("accept needs --note: say what changed and why it is intended")
    profile = profile or profile_name()
    root = root or SNAPSHOT_ROOT
    if output_dir is None:
        import build_rom as br
        output_dir = br.BUILD / "snapshots" / profile / suite
    report_path = output_dir / "report.json"
    if not report_path.is_file():
        raise SystemExit(f"no snapshot run to accept: {report_path} is missing; run the suite first")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    golden_dir = root / profile / suite
    golden_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = golden_dir / "manifest.json"
    manifest = Suite.load_manifest(manifest_path)
    records = {r["scene"]: r for r in report["scenes"]}
    chosen = scenes or [name for name, r in records.items() if r["status"] in ("changed", "new")]
    unknown = sorted(set(chosen) - set(records))
    if unknown:
        raise SystemExit(f"scenes not in the last run of '{suite}': {', '.join(unknown)}")
    accepted = []
    stamp = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    for scene in chosen:
        record = records[scene]
        if record["status"] == "missing":
            manifest["scenes"].pop(scene, None)
            (golden_dir / f"{scene}.png").unlink(missing_ok=True)
            accepted.append((scene, "removed"))
            continue
        source = output_dir / "actual" / f"{scene}.png"
        image = Image.open(source).convert("RGB")
        image.save(golden_dir / f"{scene}.png")
        manifest["scenes"][scene] = {"rgb_sha256": rgb_sha256(image), "rom_sha256": report["rom_sha256"],
                                     "configuration_id": report["configuration_id"], "accepted_at": stamp,
                                     "accepted_by": accepted_by or git_identity(), "note": note.strip()}
        accepted.append((scene, record["status"]))
    manifest["scenes"] = dict(sorted(manifest["scenes"].items()))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"suite": suite, "profile": profile, "accepted": accepted, "manifest": str(manifest_path)}


def status_table(profile: str | None = None, root: Path | None = None) -> list[dict[str, Any]]:
    import build_rom as br
    profile = profile or profile_name()
    root = root or SNAPSHOT_ROOT
    rows = []
    for suite in ALL_SUITES:
        manifest = Suite.load_manifest(root / profile / suite / "manifest.json")
        report_path = br.BUILD / "snapshots" / profile / suite / "report.json"
        report = json.loads(report_path.read_text()) if report_path.is_file() else None
        rows.append({"suite": suite, "goldens": len(manifest["scenes"]),
                     "last_run": None if report is None else report["counts"],
                     "passed": None if report is None else report["passed"]})
    return rows


def run_suite(suite: str, mode: str) -> dict[str, Any]:
    """Drive the producer that owns a suite; the producer feeds the Suite."""
    import build_rom as br
    if suite in ("tour", "world", "art"):
        from playtest import run_scenario, default_scenario
        scenario = {"tour": default_scenario(), "world": ROOT / "playtests" / "living_world.json",
                    "art": ROOT / "playtests" / "sable_art_tour.json"}[suite]
        output = {"tour": "coherence_tour", "world": "living_world", "art": "sable_art_tour"}[suite]
        return run_scenario(br.BUILD / "lupine3d.gb", br.BUILD / "lupine3d.sym", scenario,
                            br.BUILD / "playtest" / output, snapshot_mode=mode)["snapshot"]
    if suite == "sable":
        from check_sable import check
        return check(br.BUILD / "sable-v2" / "checks", snapshot_mode=mode)["snapshot"]
    if suite == "witnesses":
        from quality_witnesses import scene_corpus, capture
        rom, asm, manifest = br.make_rom()
        session = Suite("witnesses", mode=mode, rom_sha256=manifest["sha256"], configuration_id=manifest["configuration_id"])
        for scene in scene_corpus():
            _, image, _ = capture(rom, asm.labels, scene)
            session.observe(scene.name, image)
        return session.finish()
    if suite == "route":
        from playthrough import run
        run(br.BUILD / "playthrough", snapshot_mode=mode)
        return json.loads((br.BUILD / "snapshots" / profile_name() / "route" / "report.json").read_text())
    raise SystemExit(f"unknown suite: {suite}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run a producer and compare its captures with the goldens")
    run_p.add_argument("--suite", action="append", required=True, help=f"one of {', '.join(ALL_SUITES)} or 'all' (the fast suites)")
    run_p.add_argument("--mode", choices=MODES, default="check")
    diff_p = sub.add_parser("diff", help="summarise the last run of a suite")
    diff_p.add_argument("--suite", action="append", required=True)
    diff_p.add_argument("--profile")
    acc = sub.add_parser("accept", help="promote the last run's captures to goldens, with a note")
    acc.add_argument("--suite", required=True)
    acc.add_argument("--scene", action="append")
    acc.add_argument("--note", required=True)
    acc.add_argument("--profile")
    lst = sub.add_parser("list", help="goldens and last-run status per suite")
    lst.add_argument("--profile")
    args = parser.parse_args(argv)
    if args.command == "run":
        suites = [s for name in args.suite for s in (FAST_SUITES if name == "all" else (name,))]
        failures = []
        for suite in suites:
            try:
                report = run_suite(suite, args.mode)
            except SystemExit as exc:
                failures.append(str(exc)); continue
            print(json.dumps({"suite": suite, "counts": report["counts"], "passed": report["passed"]}))
        if failures:
            raise SystemExit("\n".join(failures))
    elif args.command == "diff":
        import build_rom as br
        profile = args.profile or profile_name()
        for suite in args.suite:
            path = br.BUILD / "snapshots" / profile / suite / "report.json"
            if not path.is_file():
                raise SystemExit(f"no run recorded for suite '{suite}' ({profile}); run it first")
            report = json.loads(path.read_text())
            print(f"{suite} ({profile}): {'PASS' if report['passed'] else 'DIFFERS'} {report['counts']}")
            for record in report["scenes"]:
                if record["status"] != "match":
                    print(f"  {record['scene']}: {record['status']} {record.get('changed_pixels', 0)} px bbox={record.get('bbox')}")
            print(f"  report: {path.with_suffix('.html')}")
    elif args.command == "accept":
        result = accept(args.suite, args.scene, args.note, profile=args.profile)
        print(json.dumps(result, indent=2))
    elif args.command == "list":
        for row in status_table(args.profile):
            print(json.dumps(row))


if __name__ == "__main__":
    main()
