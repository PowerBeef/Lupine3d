#!/usr/bin/env python3
"""Textured walls, host-side: the prototype gate before any SM83 is emitted.

For every pose in the corpus (the frozen witness scenes, the wall-reuse
scenes, the tour and living-world captures, and a sample of the controller
route) the lab:

1. derives the along-face texture coordinate of every physical column from
   the reference casts (`ReferenceRayHit.along_q8`) by the same
   reconstruction the tops use;
2. composes the textured frame two ways, pixel-level and by row windows, and
   requires the two to be byte-identical;
3. counts the dynamic patterns a textured frame needs, with and without a
   per-frame signature cache;
4. models the kernel's T-cycle cost against the flat compositor's, on top of
   each pose's measured per-update cycles where a report has them; and
5. renders side-by-side contact sheets (flat golden vs textured prototype).

The go criteria from the plan are evaluated at the end and written with the
numbers to `build/textured-lab/report.json`. Nothing here touches the ROM,
the emitter or the goldens.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4 import texture_reference as tx  # noqa: E402
from lupine3d_v4.reference import (reference_cast_hit, reference_cast_physical_hit,  # noqa: E402
                                   reference_pixel_descriptor_view, reference_compose_view, reference_level)

LCD_CPU_CYCLES = 140_448

# ----- prototype textures (procedural pixel art, authored once here) ----------

def make_textures() -> list[tx.Texture]:
    def panel():
        rows = []
        for v in range(8):
            row = []
            for u in range(16):
                c = 2
                if u in (0, 8): c = 3                       # panel seams
                if v == 0: c = 3                            # top rail
                if v in (3, 4) and u in (3, 4, 11, 12): c = 1   # rivets
                if v == 7 and u % 4 == 2: c = 1             # lower bolts
                row.append(c)
            rows.append(tuple(row))
        return tx.Texture("steel_panel", tuple(rows))

    def grille():
        rows = []
        for v in range(8):
            row = []
            for u in range(16):
                c = 2
                if (u + v) % 4 == 0: c = 1
                if v % 4 == 1 and u % 2 == 0: c = 3
                if u in (0, 15): c = 3
                row.append(c)
            rows.append(tuple(row))
        return tx.Texture("machinery_grille", tuple(rows))

    def door():
        rows = []
        for v in range(8):
            row = []
            for u in range(16):
                c = 2
                if u in (7, 8): c = 3                       # spine
                if v in (1, 6) and 2 <= u <= 13: c = 3      # bands
                if v in (3, 4) and u in (5, 10): c = 1      # bolts
                if u in (0, 15): c = 1                      # jambs
                row.append(c)
            rows.append(tuple(row))
        return tx.Texture("door_plate", tuple(rows))
    return [panel(), grille(), door()]


PROFILE_TEXTURE = {0: 0, 1: 1, 2: 2}   # surface profile structure/machinery/door -> texture


# ----- corpus ---------------------------------------------------------------

def tour_poses():
    for name in ("sable_v10_coherence_tour.json", "living_world.json"):
        scenario = json.loads((ROOT / "playtests" / name).read_text())
        for index, action in enumerate(scenario["actions"]):
            if "pose" in action:
                yield f"{name.split('.')[0]}:{index:02d}", tuple(action["pose"]), None, None


def witness_poses():
    from quality_witnesses import scene_corpus
    for scene in scene_corpus():
        if scene.art_frame > 0:
            continue  # the art frames repeat one pose
        doors = {(x, y): (1, aperture) for x, y, _, aperture in scene.doors}
        yield f"witness:{scene.name}", scene.pose, scene.grid, doors


def wall_reuse_poses():
    from benchmark_wall_reuse import scenes
    for index, scene in enumerate(scenes()):
        doors = {(d.x, d.y): (1, scene["fraction"]) for d in br.ACTIVE_LEVEL.doors}
        yield f"wall_reuse:{index:02d}", tuple(scene["pose"]), None, doors


def route_poses(every: int):
    path = br.BUILD / "playthrough" / "report.json"
    if not path.is_file():
        return
    report = json.loads(path.read_text())
    bounds, start = [], 0
    for sector in report["sectors"]:
        bounds.append((start, start + sector["updates"], sector["index"])); start += sector["updates"]
    for i, update in enumerate(report["updates"]):
        if i % every:
            continue
        level = next((index for lo, hi, index in bounds if lo <= i < hi), None)
        if level is None:
            continue
        pose = (update["pose"]["x_q8"], update["pose"]["y_q8"], update["pose"]["angle"])
        yield f"route:{i:04d}", pose, br.CAMPAIGN[level].grid, {}, update["cycles"], level


# ----- descriptors and texture coordinates ----------------------------------

def textured_columns(pose, grid, doors) -> tuple[list[tx.TexturedColumn], dict]:
    px, py, yaw = pose
    view = reference_pixel_descriptor_view(px, py, yaw, grid, doors)
    tops, styles, keys, alongs, casts, recasts, events, depths, segments, pixel_segments, surfaces = view
    hits = [reference_cast_hit(px, py, yaw, i, grid, doors) for i in range(br.RAYS)]
    ray_keys = [h.face_key for h in hits]
    ray_u = [h.along_q8 for h in hits]
    edge_u = {}
    for i in range(br.RAYS - 1):
        if ray_keys[i] == ray_keys[i + 1] and hits[i].segment_id == hits[i + 1].segment_id:
            continue
        for pixel in (i * 2 + 1, i * 2 + 2):
            edge_u[pixel] = reference_cast_physical_hit(px, py, yaw, pixel, grid, doors).along_q8
    pixel_u = tx.expand_pixel_u(ray_u, ray_keys, [h.segment_id for h in hits], edge_u)
    # Face side from the hit: axis 0 west/east by sx, axis 1 north/south by sy.
    sides = []
    for i in range(br.RAYS):
        h = hits[i]
        side = (0 if h.dx > 0 else 1) if h.axis == 0 else (2 if h.dy > 0 else 3)
        sides += [side, side]
    columns = []
    for x in range(br.PHYSICAL_COLUMNS):
        profile = surfaces[x]
        columns.append(tx.TexturedColumn(tops[x], styles[x], keys[x], PROFILE_TEXTURE.get(profile, 0),
                                         tx.face_texel_column(pixel_u[x], sides[x])))
    return columns, {"tops": tops, "styles": styles, "casts": casts}


# ----- cycle model ------------------------------------------------------------

KERNEL = {"interior": 700, "boundary": 1300, "seam": 600, "u_per_ray": 70, "u_per_pixel": 12,
          "hblank_block": 64, "flat_dynamic": 6700, "flat_atlas_hit": 300}


def model_delta(stats: dict, flat_dynamic: int, flat_atlas_hits: int, textured_patterns: int) -> int:
    textured = (stats["wall_tiles"] - stats["boundary_tiles"]) * KERNEL["interior"] \
        + stats["boundary_tiles"] * KERNEL["boundary"] + stats["seam_tiles"] * KERNEL["seam"]
    textured += br.RAYS * KERNEL["u_per_ray"] + br.PHYSICAL_COLUMNS * KERNEL["u_per_pixel"]
    textured += max(0, textured_patterns - flat_dynamic) * KERNEL["hblank_block"]
    flat = flat_dynamic * KERNEL["flat_dynamic"] + flat_atlas_hits * KERNEL["flat_atlas_hit"]
    return textured - flat


def flat_atlas_hits(tops, styles) -> int:
    """How many of today's wall tiles come from the exact atlas (cheap) rather
    than composition: total non-static wall tiles minus dynamic compositions."""
    from lupine3d_v4.reference import reference_tile_signature_and_bytes, tile_atlas_signature_map
    atlas = tile_atlas_signature_map(); hits = 0
    for tile_col in range(20):
        col_tops = tops[tile_col * 8:tile_col * 8 + 8]; col_styles = styles[tile_col * 8:tile_col * 8 + 8]
        min_top, max_top = min(col_tops), max(col_tops)
        for tile_row in range(br.FOLDED_ROWS):
            y0 = tile_row * 8
            if y0 + 7 < min_top or y0 >= br.VIEW_HEIGHT - min_top: continue
            if y0 >= max_top and y0 + 7 < br.VIEW_HEIGHT - max_top: continue  # static seam tile
            signature, _ = reference_tile_signature_and_bytes(col_tops, col_styles, y0)
            hits += signature in atlas
    return hits


# ----- rendering -------------------------------------------------------------

PALETTES = {  # (upper palette index) -> RGB of colours 0..3, from build_rom's tables
    0: ((8, 16, 24), (41, 49, 57), (115, 140, 148), (49, 74, 90)),
    3: ((8, 16, 24), (41, 49, 57), (24, 107, 132), (123, 222, 206)),
    5: ((8, 16, 24), (41, 49, 57), (82, 115, 99), (33, 66, 57)),
}
PROFILE_PALETTE = {0: 0, 1: 5, 2: 3}


def render_textured(textures, columns, *, outline=True) -> Image.Image:
    image = Image.new("RGB", (160, br.VIEW_HEIGHT))
    pixels = image.load()
    for tile_col in range(20):
        cols = columns[tile_col * 8:tile_col * 8 + 8]
        half = tx.column_half(cols)
        for i, c in enumerate(cols):
            x = tile_col * 8 + i
            palette = PALETTES[PROFILE_PALETTE.get({0: 0, 1: 1, 2: 2}.get(c.texture, 0), 0)]
            for y in range(br.HORIZON):
                colour = tx.wall_pixel(textures, c, half, y, outline=outline)
                pixels[x, y] = palette[colour]
                mirrored = tx.wall_pixel(textures, c, half, y, outline=outline)
                # Lower half: the Y-flip mirror, with palette 2's colour 0 = floor.
                lower = (41, 49, 57) if mirrored == 0 else palette[mirrored]
                pixels[x, br.VIEW_HEIGHT - 1 - y] = lower
    return image


def contact_sheet(rows: list[tuple[str, Image.Image, Image.Image]], output: Path) -> None:
    scale, margin, label = 2, 10, 18
    w, h = 160 * scale, br.VIEW_HEIGHT * scale
    sheet = Image.new("RGB", (margin * 3 + w * 2, margin + len(rows) * (h + label + margin)), (12, 15, 21))
    draw = ImageDraw.Draw(sheet)
    for index, (name, flat, textured) in enumerate(rows):
        y = margin + index * (h + label + margin)
        sheet.paste(flat.resize((w, h), Image.Resampling.NEAREST), (margin, y))
        sheet.paste(textured.resize((w, h), Image.Resampling.NEAREST), (margin * 2 + w, y))
        draw.text((margin, y + h + 2), f"{name}  flat (golden) | textured prototype", fill=(229, 183, 96))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def golden_world(name: str) -> Image.Image | None:
    """The accepted flat frame for a tour/world capture, cropped to the world."""
    suite, index = name.split(":")
    suite = {"sable_v10_coherence_tour": "tour", "living_world": "world"}.get(suite)
    if suite is None:
        return None
    scenario = json.loads((ROOT / "playtests" / ("sable_v10_coherence_tour.json" if suite == "tour" else "living_world.json")).read_text())
    captures = [a for a in scenario["actions"] if "capture" in a]
    action = scenario["actions"][int(index)]
    if "capture" not in action:
        return None
    number = captures.index(action) + 1
    path = ROOT / "snapshots" / "slim-sable-v2" / suite / f"{number:02d}_{action['capture']}.png"
    return Image.open(path).convert("RGB").crop((0, 0, 160, br.VIEW_HEIGHT)) if path.is_file() else None


# ----- main -------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", type=Path, default=br.BUILD / "textured-lab")
    p.add_argument("--route-every", type=int, default=8, help="sample every Nth controller-route update")
    p.add_argument("--no-outline", action="store_true")
    args = p.parse_args()
    out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    textures = make_textures()
    windows = tx.make_row_windows(textures)
    outline = not args.no_outline

    rows, sheet_rows, mismatches = [], [], 0
    corpus = list(tour_poses()) + list(witness_poses()) + list(wall_reuse_poses())
    corpus = [(name, pose, grid, doors, None, None) for name, pose, grid, doors in corpus] + list(route_poses(args.route_every))
    flat_cycles = {}
    for report_name in ("coherence_tour", "living_world"):
        path = br.BUILD / "playtest" / report_name / "report.json"
        if path.is_file():
            for update in json.loads(path.read_text())["updates"]:
                flat_cycles[(update["pose"]["x_q8"], update["pose"]["y_q8"], update["pose"]["angle"])] = update["cycles"]
    for name, pose, grid, doors, cycles, level in corpus:
        if level is not None:
            br.select_reference_level(level)
        else:
            br.select_reference_level(0)
        try:
            columns, info = textured_columns(pose, grid, doors)
        except Exception as exc:  # a pose the reference cannot cast (e.g. inside a wall) is reported, not hidden
            rows.append({"scene": name, "error": repr(exc)}); continue
        dynamic, view_map, count, overflow, stats = tx.compose_pixels(textures, columns, outline=outline)
        by_windows = tx.compose_windows(textures, columns, windows, outline=outline)
        # The kernel composes the affine coordinates; prove its table lookup equals
        # the pixel-level composition of those same affine coordinates.
        affine_dynamic, _, affine_count, _, _ = tx.compose_pixels(textures, tx.affine_columns(columns), outline=outline)
        exact = by_windows == affine_dynamic
        mismatches += not exact
        flat_dynamic, _, flat_count, _ = reference_compose_view(info["tops"], info["styles"])
        raw_patterns = stats["wall_tiles"]
        hits = flat_atlas_hits(info["tops"], info["styles"])
        delta = model_delta(stats, flat_count, hits, affine_count)
        base = cycles if cycles is not None else flat_cycles.get(tuple(pose))
        row = {"scene": name, "pose": pose, "level": level, "windows_equal_pixels": exact,
               "patterns_raw": raw_patterns, "patterns_unique": affine_count, "patterns_exact_u": count,
               "flat_dynamic": flat_count, "flat_atlas_hits": hits, "wall_tiles": stats["wall_tiles"],
               "boundary_tiles": stats["boundary_tiles"], "seam_tiles": stats["seam_tiles"], "overflow": overflow,
               "model_delta_cycles": delta, "base_cycles": base,
               "intervals_before": None if base is None else math.ceil(base / LCD_CPU_CYCLES),
               "intervals_after": None if base is None else math.ceil((base + delta) / LCD_CPU_CYCLES)}
        rows.append(row)
        if len(sheet_rows) < 24 and (name.startswith("sable_v10") or name.startswith("living_world") or name.startswith("witness:finite_door") or name.startswith("witness:shallow")):
            golden = golden_world(name)
            flat = golden if golden is not None else Image.new("RGB", (160, br.VIEW_HEIGHT), (30, 30, 30))
            sheet_rows.append((name, flat, render_textured(textures, tx.affine_columns(columns), outline=outline)))
            render_textured(textures, columns, outline=outline).resize((640, br.VIEW_HEIGHT * 4), Image.Resampling.NEAREST).save(out / f"{name.replace(':', '_')}_exact_u_4x.png")
    contact_sheet(sheet_rows, out / "contact_sheet.png")

    valid = [r for r in rows if "error" not in r]
    uniques = sorted(r["patterns_unique"] for r in valid)
    raws = sorted(r["patterns_raw"] for r in valid)
    p95 = uniques[int(0.95 * (len(uniques) - 1))]
    deltas = [r["model_delta_cycles"] for r in valid]
    with_base = [r for r in valid if r["base_cycles"] is not None]
    unchanged = sum(r["intervals_before"] == r["intervals_after"] for r in with_base)
    rom_bytes = tx.window_table_bytes(len(textures)) + len(tx.make_v_lut()) + 16384 + 256
    projected = {}
    sustained = br.BUILD / "sustained_final"
    for scenario in ("turning", "walking", "two_actor_corner", "walking_turning", "moving_fire"):
        path = sustained / scenario / "motion_benchmark.json"
        if path.is_file():
            case = json.loads(path.read_text())["cases"][scenario]["candidate"]
            mean = case["full_mean_cycles"]
            # Rate follows the interval quantisation: model the mean update as
            # ceil((mean + delta)/interval) intervals, as the audit found.
            before = LCD_CPU_CYCLES * math.ceil(mean / LCD_CPU_CYCLES)
            after = LCD_CPU_CYCLES * math.ceil((mean + statistics.fmean(deltas)) / LCD_CPU_CYCLES)
            projected[scenario] = {"measured_hz": case["full_geometry_updates_hz"],
                                   "projected_hz": round(case["full_geometry_updates_hz"] * before / after, 2)}
    before_total = sum(r["intervals_before"] for r in with_base)
    after_total = sum(r["intervals_after"] for r in with_base)
    criteria = {
        "windows_equal_pixels_everywhere": mismatches == 0,
        "mean_delta_under_70k": statistics.fmean(deltas) <= 70_000,
        "delta_p95_under_one_interval": sorted(deltas)[int(0.95 * (len(deltas) - 1))] <= LCD_CPU_CYCLES,
        # Frames near an interval boundary flip either way; what matters for
        # throughput is the modelled total, not how many individual frames moved.
        "intervals_net_increase_under_2pct": (after_total <= before_total * 1.02) if with_base else None,
        "patterns_p95_under_114": p95 <= 114,
        "patterns_max_under_224": max(uniques) <= 224,
        "rom_under_160k": rom_bytes <= 160 * 1024,
        "no_overflow": not any(r["overflow"] for r in valid),
    }
    report = {"schema": "lupine3d.textured-lab.v1", "textures": [t.name for t in textures],
              "corpus": len(rows), "errors": sum("error" in r for r in rows),
              "patterns": {"unique_p50": uniques[len(uniques) // 2], "unique_p95": p95, "unique_max": max(uniques),
                           "raw_p95": raws[int(0.95 * (len(raws) - 1))], "raw_max": max(raws)},
              "model_delta": {"mean": statistics.fmean(deltas), "p95": sorted(deltas)[int(0.95 * (len(deltas) - 1))], "max": max(deltas)},
              "intervals": {"with_base": len(with_base), "unchanged": unchanged, "before_total": before_total,
                            "after_total": after_total, "net_change_pct": round((after_total / before_total - 1) * 100, 2) if with_base else None},
              "rom_bytes": rom_bytes, "window_table_bytes_per_texture": tx.window_table_bytes(1),
              "kernel_model": KERNEL, "projected_sustained": projected, "criteria": criteria,
              "go": all(v for v in criteria.values() if v is not None), "rows": rows}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
