#!/usr/bin/env python3
"""Deterministic retained-baseline -> current geometry/material investigation.

The accuracy path compares both ROM models against a floating 160-column
camera-plane oracle over the established 3,048-view corpus.  The visual path
executes the emitted ROMs in the project SM83/CGB harness and captures their
actual tile/attribute output at identical poses.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research"))

import build_rom as v3  # noqa: E402
import build_rom_v2 as v2  # noqa: E402
import geometry_v2_lab as geometry  # noqa: E402
from sm83emu import CGB  # noqa: E402

RESULTS = ROOT / "research" / "results"
DOUBLE_SPEED_HZ = 8_388_608


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def summarize_errors(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean_px": statistics.fmean(values),
        "p95_px": percentile(values, 0.95),
        "p99_px": percentile(values, 0.99),
        "max_px": max(values),
    }


def expand_pairs(values: Sequence[int]) -> list[int]:
    return [item for value in values for item in (int(value), int(value))]


def segments_for(keys: Sequence[int], alongs: Sequence[int], player_angle: int,
                 offsets_blob: bytes) -> list[str]:
    offsets = [
        int.from_bytes(offsets_blob[i:i + 2], "little", signed=True)
        for i in range(0, len(offsets_blob), 2)
    ]
    tables = v3.make_tables()
    dx_table = [geometry.signed8(value) for value in tables["ray_dx"]]
    dy_table = [geometry.signed8(value) for value in tables["ray_dy"]]
    result: list[str] = []
    for index, (key, along) in enumerate(zip(keys, alongs)):
        axis = (key >> 7) & 1
        material = (key >> 5) & 3
        plane = key & 31
        direction = ((player_angle << 2) + offsets[index]) & 0x3FF
        dx, dy = dx_table[direction], dy_table[direction]
        if axis == 0:
            cell_x, cell_y = (plane if dx > 0 else plane - 1), along
        else:
            cell_x, cell_y = along, (plane if dy > 0 else plane - 1)
        result.append(geometry.segment_for(cell_x, cell_y, axis, dx, dy, material))
    return result


def benchmark_rom_cycles(poses: Sequence[tuple[int, int, int]]) -> dict[str, float]:
    rom, assembler, _ = v3.make_rom()
    cgb = CGB(rom, assembler.labels)
    cgb.run(until_pc=assembler.labels["main_loop"], max_steps=5_000_000)
    totals: list[int] = []
    cast_cycles: list[int] = []
    render_cycles: list[int] = []
    for x_q8, y_q8, angle in poses:
        cgb.write16(v3.PLAYER_XL, x_q8)
        cgb.write16(v3.PLAYER_YL, y_q8)
        cgb.write8(v3.ANGLE, angle)
        start = cgb.cycles
        cgb.call_subroutine("cast_all", max_steps=3_000_000)
        after_cast = cgb.cycles
        cgb.call_subroutine("render_view", max_steps=3_000_000)
        after_render = cgb.cycles
        cast_cycles.append(after_cast - start)
        render_cycles.append(after_render - after_cast)
        totals.append(after_render - start)
    return {
        "pose_count": len(poses),
        "mean_cast_cycles": statistics.fmean(cast_cycles),
        "max_cast_cycles": max(cast_cycles),
        "mean_render_cycles": statistics.fmean(render_cycles),
        "max_render_cycles": max(render_cycles),
        "mean_cast_plus_render_cycles": statistics.fmean(totals),
        "conservative_updates_per_second": DOUBLE_SPEED_HZ / max(totals),
    }


def run(*, measure_cycles: bool = True) -> dict[str, object]:
    # The floating and v2 oracles describe solid cell faces. Passing this
    # explicit grid suppresses the current model's implicit finite-door setup;
    # comparing a door centre plane to a cell face is a different experiment.
    static_grid = bytes(geometry.GRID_BYTES)
    if static_grid != v3.make_map():
        raise ValueError("accuracy comparison requires the retained benchmark map")
    positions = geometry.corpus_positions()
    angles = range(0, 256, 4)
    v2_errors: list[float] = []
    v3_errors: list[float] = []
    common_viewport_errors: list[float] = []
    v2_wrong_segments = v3_wrong_segments = 0
    v2_wrong_materials = v3_wrong_materials = 0
    v2_casts: list[int] = []
    v3_casts: list[int] = []
    edge_recasts: list[int] = []
    material_events: list[int] = []
    dynamic_tiles: list[int] = []
    split_pairs: list[int] = []
    overflow_views = 0
    views = 0

    for x_q8, y_q8 in positions:
        for angle in angles:
            reference = [
                geometry.float_camera_hit(x_q8 / 256.0, y_q8 / 256.0, angle, x + 0.5)
                for x in range(v3.PHYSICAL_COLUMNS)
            ]
            reference_tops = [hit.top for hit in reference]
            # v2 retains its 48-pixel horizon. Compare the current renderer
            # with its own projection origin, including near-wall clipping;
            # translating already clipped legacy tops would be incorrect.
            current_reference_tops = [
                geometry.float_camera_hit(x_q8 / 256.0, y_q8 / 256.0, angle,
                                          x + 0.5, horizon=v3.HORIZON).top
                for x in range(v3.PHYSICAL_COLUMNS)
            ]
            reference_segments = [hit.segment for hit in reference]
            reference_materials = [hit.material for hit in reference]

            old = v2.reference_adaptive_descriptor_view(x_q8, y_q8, angle)
            old_tops = expand_pairs(old[0])
            old_keys = expand_pairs(old[2])
            old_alongs = expand_pairs(old[3])
            old_pair_offsets = v2.make_tables()["ray_offsets"]
            old_offsets = b"".join(old_pair_offsets[i:i + 2] * 2 for i in range(0, len(old_pair_offsets), 2))
            old_segments = segments_for(old_keys, old_alongs, angle, old_offsets)
            old_materials = [(key >> 5) & 3 for key in old_keys]

            new = v3.reference_pixel_descriptor_view(x_q8, y_q8, angle, static_grid)
            new_tops, new_styles, new_keys, new_alongs = new[:4]
            new_segments = segments_for(new_keys, new_alongs, angle, v3.make_tables()["physical_offsets"])
            new_materials = [(key >> 5) & 3 for key in new_keys]

            v2_errors.extend(abs(float(a) - b) for a, b in zip(old_tops, reference_tops))
            v3_errors.extend(abs(float(a) - b) for a, b in zip(new_tops, current_reference_tops))
            # Historical improvement gates compare the same 96-pixel window.
            # Newly exposed near-wall edges are reported above, separately.
            shift = v3.HORIZON - 48
            common_viewport_errors.extend(
                abs(max(0.0, float(a) - shift) - max(0.0, b - shift))
                for a, b in zip(new_tops, current_reference_tops)
            )
            v2_wrong_segments += sum(a != b for a, b in zip(old_segments, reference_segments))
            v3_wrong_segments += sum(a != b for a, b in zip(new_segments, reference_segments))
            v2_wrong_materials += sum(a != b for a, b in zip(old_materials, reference_materials))
            v3_wrong_materials += sum(a != b for a, b in zip(new_materials, reference_materials))
            v2_casts.append(old[4])
            v3_casts.append(new[4])
            edge_recasts.append(new[5])
            material_events.append(new[6])
            split_pairs.append(sum(
                new_tops[i] != new_tops[i + 1] or new_styles[i] != new_styles[i + 1]
                for i in range(0, v3.PHYSICAL_COLUMNS, 2)
            ))
            _, _, count, overflow = v3.reference_compose_view(new_tops, new_styles)
            dynamic_tiles.append(count)
            overflow_views += int(overflow)
            views += 1

    samples = views * v3.PHYSICAL_COLUMNS
    old_stats = summarize_errors(v2_errors)
    new_stats = summarize_errors(v3_errors)
    common_stats = summarize_errors(common_viewport_errors)
    poses = [
        (0x0180, 0x0180, 0), (0x0680, 0x0120, 64),
        (0x0880, 0x0580, 144), (0x0D80, 0x0D80, 224),
        (0x08E0, 0x0180, 16), (0x0520, 0x0B80, 192),
    ]
    return {
        "configuration": {
            "scope": "static-cell host geometry; finite doors and runtime timing are qualified separately",
            "static_cell_geometry": True,
            "legacy_horizon": 48,
            "current_horizon": v3.HORIZON,
            "level_grid_sha256": hashlib.sha256(static_grid).hexdigest(),
            "benchmark_rom_sha256": hashlib.sha256(v3.make_rom()[0]).hexdigest(),
        },
        "corpus": {"views": views, "physical_column_samples": samples},
        "common_96_pixel_window": {
            **common_stats,
            "mean_top_error_reduction_pct": 100.0 * (1.0 - common_stats["mean_px"] / old_stats["mean_px"]),
        },
        "v0.2.2": {
            **old_stats,
            "wrong_segment_pct": 100.0 * v2_wrong_segments / samples,
            "wrong_material_pct": 100.0 * v2_wrong_materials / samples,
            "mean_casts": statistics.fmean(v2_casts),
        },
        "current": {
            **new_stats,
            "wrong_segment_pct": 100.0 * v3_wrong_segments / samples,
            "wrong_material_pct": 100.0 * v3_wrong_materials / samples,
            "mean_total_casts": statistics.fmean(v3_casts),
            "mean_edge_recasts": statistics.fmean(edge_recasts),
            "max_edge_recasts": max(edge_recasts),
            "mean_material_events": statistics.fmean(material_events),
            "max_material_events": max(material_events),
            "mean_split_pairs": statistics.fmean(split_pairs),
            "mean_dynamic_tiles": statistics.fmean(dynamic_tiles),
            "max_dynamic_tiles": max(dynamic_tiles),
            "overflow_views": overflow_views,
        },
        "improvement": {
            "mean_top_error_reduction_pct": 100.0 * (1.0 - new_stats["mean_px"] / old_stats["mean_px"]),
            "p95_top_error_reduction_pct": 100.0 * (1.0 - new_stats["p95_px"] / old_stats["p95_px"]),
            "p99_top_error_reduction_pct": 100.0 * (1.0 - new_stats["p99_px"] / old_stats["p99_px"]),
            "wrong_segment_reduction_pct": 100.0 * (1.0 - v3_wrong_segments / v2_wrong_segments),
            "wrong_material_reduction_pct": 100.0 * (1.0 - v3_wrong_materials / v2_wrong_materials),
        },
        **({"representative_rom_cycles": benchmark_rom_cycles(poses)} if measure_cycles else {}),
    }


def render_rom_pose(builder: object, pose: tuple[int, int, int]) -> Image.Image:
    rom, assembler, _ = builder.make_rom()
    cgb = CGB(rom, assembler.labels)
    cgb.run(until_pc=assembler.labels["main_loop"], max_steps=5_000_000)
    x_q8, y_q8, angle = pose
    cgb.write16(builder.PLAYER_XL, x_q8)
    cgb.write16(builder.PLAYER_YL, y_q8)
    cgb.write8(builder.ANGLE, angle)
    cgb.call_subroutine("cast_all", max_steps=3_000_000)
    cgb.call_subroutine("render_view", max_steps=3_000_000)
    cgb.call_subroutine("upload_hidden_page", max_steps=1_000_000)
    return cgb.render_screen()


def make_comparison(path: Path) -> None:
    poses = [(0x0180, 0x0180, 0), (0x08E0, 0x0180, 16), (0x0880, 0x0580, 144)]
    scale = 2
    margin = 12
    label_height = 20
    width = margin * 3 + 160 * scale * 2
    height = margin * 4 + (144 * scale + label_height) * len(poses)
    sheet = Image.new("RGB", (width, height), (12, 15, 21))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, 4), "v0.2.2 — pair materials", fill=(190, 198, 215))
    draw.text((margin * 2 + 160 * scale, 4), "current — hybrid coherent renderer", fill=(229, 183, 96))
    y = margin + label_height
    for pose in poses:
        before = render_rom_pose(v2, pose).resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
        after = render_rom_pose(v3, pose).resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
        sheet.paste(before, (margin, y))
        sheet.paste(after, (margin * 2 + 160 * scale, y))
        draw.text((margin, y + 144 * scale + 2), f"pose {pose}", fill=(130, 141, 162))
        y += 144 * scale + label_height + margin
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def write_csv(results: dict[str, object], path: Path) -> None:
    rows = []
    for version in ("v0.2.2", "current"):
        data = results[version]
        rows.append({"version": version, **data})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=sorted({key for row in rows for key in row}),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RESULTS)
    parser.add_argument("--accuracy-only", action="store_true", help="run the static host corpus without legacy ROM probes")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = run(measure_cycles=not args.accuracy_only)
    (args.output_dir / "rendering_v3_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    write_csv(results, args.output_dir / "rendering_v3_accuracy.csv")
    if not args.accuracy_only:
        make_comparison(args.output_dir / "rendering_v3_before_after.png")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
