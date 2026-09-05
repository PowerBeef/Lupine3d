#!/usr/bin/env python3
"""Forensic corpus for rare Lupine 3D geometry-tail failures.

The normal accuracy report summarizes millions of columns.  This lab preserves
the exceptional columns themselves so a large maximum can never hide behind an
excellent mean.  Each record includes the exact pose, physical column, float
oracle, integer descriptor, visible segment identities, local map cells, and a
small visual comparison.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import hashlib
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "research")]

import build_rom as engine  # noqa: E402
import geometry_v2_lab as geometry  # noqa: E402

RESULTS = ROOT / "research" / "results"


@dataclass(frozen=True)
class TailRecord:
    severity: float
    top_error_px: float
    wrong_segment: bool
    wrong_material: bool
    player_x_q8: int
    player_y_q8: int
    angle: int
    physical_column: int
    actual_top: int
    expected_top: float
    actual_style: int
    actual_face_key: int
    actual_along: int
    actual_segment: str
    expected_axis: int
    expected_material: int
    expected_cell_x: int
    expected_cell_y: int
    expected_segment: str
    pair_index: int
    total_casts: int
    edge_recasts: int
    map_neighborhood: tuple[str, ...]


def _physical_directions(angle: int) -> list[tuple[int, int]]:
    tables = engine.make_tables()
    offsets = [
        int.from_bytes(tables["physical_offsets"][i:i + 2], "little", signed=True)
        for i in range(0, len(tables["physical_offsets"]), 2)
    ]
    dx_table = [geometry.signed8(value) for value in tables["ray_dx"]]
    dy_table = [geometry.signed8(value) for value in tables["ray_dy"]]
    return [
        (dx_table[((angle << engine.RAY_PLAYER_SHIFT) + offset) & (engine.RAY_DIRECTION_COUNT - 1)],
         dy_table[((angle << engine.RAY_PLAYER_SHIFT) + offset) & (engine.RAY_DIRECTION_COUNT - 1)])
        for offset in offsets
    ]


def _actual_segments(keys: Sequence[int], alongs: Sequence[int], angle: int) -> list[str]:
    result: list[str] = []
    for (key, along), (dx, dy) in zip(zip(keys, alongs), _physical_directions(angle)):
        axis = (key >> 7) & 1
        material = (key >> 5) & 3
        plane = key & 31
        if axis == 0:
            cell_x, cell_y = (plane if dx > 0 else plane - 1), along
        else:
            cell_x, cell_y = along, (plane if dy > 0 else plane - 1)
        result.append(geometry.segment_for(cell_x, cell_y, axis, dx, dy, material))
    return result


def _map_neighborhood(grid: bytes, player_x_q8: int, player_y_q8: int,
                      radius: int = 2) -> tuple[str, ...]:
    cx, cy = player_x_q8 >> 8, player_y_q8 >> 8
    rows: list[str] = []
    for y in range(cy - radius, cy + radius + 1):
        values: list[str] = []
        for x in range(cx - radius, cx + radius + 1):
            if not (0 <= x < 16 and 0 <= y < 16):
                values.append("#")
            elif x == cx and y == cy:
                values.append("P")
            else:
                values.append(str(grid[y * 16 + x]))
        rows.append("".join(values))
    return tuple(rows)


def inspect_pose(player_x_q8: int, player_y_q8: int, angle: int,
                 *, threshold_px: float = 8.0, grid: bytes | None = None
                 ) -> tuple[list[TailRecord], dict[str, float | int]]:
    """Return every exceptional column and deterministic pose counters."""
    cells = grid if grid is not None else engine.reference_grid()
    oracle = [
        geometry.float_camera_hit(
            player_x_q8 / 256.0, player_y_q8 / 256.0, angle, column + 0.5,
        )
        for column in range(engine.PHYSICAL_COLUMNS)
    ]
    actual = engine.reference_pixel_descriptor_view(
        player_x_q8, player_y_q8, angle, cells,
    )
    tops, styles, keys, alongs = actual[:4]
    segments = _actual_segments(keys, alongs, angle)
    neighborhood = _map_neighborhood(cells, player_x_q8, player_y_q8)
    records: list[TailRecord] = []
    errors: list[float] = []
    wrong_segments = wrong_materials = 0
    for column, (top, style, key, along, segment, expected) in enumerate(
        zip(tops, styles, keys, alongs, segments, oracle)
    ):
        error = abs(float(top) - expected.top)
        material = (key >> 5) & 3
        wrong_segment = segment != expected.segment
        wrong_material = material != expected.material
        errors.append(error)
        wrong_segments += int(wrong_segment)
        wrong_materials += int(wrong_material)
        if error < threshold_px and not wrong_segment and not wrong_material:
            continue
        severity = max(error, 16.0 if wrong_segment else 0.0, 8.0 if wrong_material else 0.0)
        records.append(TailRecord(
            severity=severity,
            top_error_px=error,
            wrong_segment=wrong_segment,
            wrong_material=wrong_material,
            player_x_q8=player_x_q8,
            player_y_q8=player_y_q8,
            angle=angle,
            physical_column=column,
            actual_top=top,
            expected_top=expected.top,
            actual_style=style,
            actual_face_key=key,
            actual_along=along,
            actual_segment=segment,
            expected_axis=expected.axis,
            expected_material=expected.material,
            expected_cell_x=expected.cell_x,
            expected_cell_y=expected.cell_y,
            expected_segment=expected.segment,
            pair_index=column // 2,
            total_casts=actual[4],
            edge_recasts=actual[5],
            map_neighborhood=neighborhood,
        ))
    return records, {
        "mean_top_error_px": statistics.fmean(errors),
        "max_top_error_px": max(errors),
        "wrong_segments": wrong_segments,
        "wrong_materials": wrong_materials,
        "total_casts": actual[4],
        "edge_recasts": actual[5],
    }


def scan(*, threshold_px: float = 8.0, top_count: int = 64,
         angle_step: int = 4,
         positions: Iterable[tuple[int, int]] | None = None
         ) -> tuple[dict[str, object], list[TailRecord]]:
    """Scan the deterministic corpus while retaining only bounded evidence."""
    selected_positions = list(positions if positions is not None else geometry.corpus_positions())
    top_heap: list[tuple[float, int, TailRecord]] = []
    serial = 0
    view_count = column_count = tail_count = 0
    wrong_segments = wrong_materials = 0
    tail_same_segment = 0
    maximum_error = 0.0
    affected_poses: set[tuple[int, int, int]] = set()
    for x_q8, y_q8 in selected_positions:
        for angle in range(0, 256, angle_step):
            records, summary = inspect_pose(x_q8, y_q8, angle, threshold_px=threshold_px)
            view_count += 1
            column_count += engine.PHYSICAL_COLUMNS
            wrong_segments += int(summary["wrong_segments"])
            wrong_materials += int(summary["wrong_materials"])
            maximum_error = max(maximum_error, float(summary["max_top_error_px"]))
            for record in records:
                if record.top_error_px >= threshold_px:
                    tail_count += 1
                    tail_same_segment += int(not record.wrong_segment)
                affected_poses.add((x_q8, y_q8, angle))
                item = (record.severity, serial, record)
                serial += 1
                if len(top_heap) < top_count:
                    heapq.heappush(top_heap, item)
                elif item > top_heap[0]:
                    heapq.heapreplace(top_heap, item)
    top_records = [item[2] for item in sorted(top_heap, reverse=True)]
    report: dict[str, object] = {
        "threshold_px": threshold_px,
        "corpus": {
            "positions": len(selected_positions),
            "angle_step": angle_step,
            "views": view_count,
            "physical_columns": column_count,
        },
        "tail": {
            "maximum_top_error_px": maximum_error,
            "columns_at_or_above_threshold": tail_count,
            "tail_columns_with_correct_segment": tail_same_segment,
            "wrong_segment_columns": wrong_segments,
            "wrong_material_columns": wrong_materials,
            "affected_poses": len(affected_poses),
            "retained_records": len(top_records),
        },
        "diagnosis": (
            "No columns crossed the configured top-error threshold."
            if tail_count == 0
            else "Large top-error tails are occlusion/segment-selection events."
            if tail_same_segment == 0
            else "The tail includes same-segment projection errors and needs arithmetic analysis."
        ),
        "records": [asdict(record) for record in top_records],
    }
    return report, top_records


def write_csv(records: Sequence[TailRecord], path: Path) -> None:
    rows = [asdict(record) | {"map_neighborhood": "/".join(record.map_neighborhood)}
            for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_sheet(records: Sequence[TailRecord], path: Path, *, pose_count: int = 8) -> None:
    """Draw actual/oracle silhouettes for the worst unique poses."""
    poses: list[tuple[int, int, int]] = []
    for record in records:
        pose = (record.player_x_q8, record.player_y_q8, record.angle)
        if pose not in poses:
            poses.append(pose)
        if len(poses) == pose_count:
            break
    panel_w, panel_h = 360, 150
    sheet = Image.new("RGB", (panel_w, panel_h * max(1, len(poses))), (11, 14, 19))
    draw = ImageDraw.Draw(sheet)
    for panel, (x_q8, y_q8, angle) in enumerate(poses):
        y_base = panel * panel_h
        expected = [
            geometry.float_camera_hit(x_q8 / 256.0, y_q8 / 256.0, angle, x + 0.5)
            for x in range(engine.PHYSICAL_COLUMNS)
        ]
        actual = engine.reference_pixel_descriptor_view(x_q8, y_q8, angle)
        segments = _actual_segments(actual[2], actual[3], angle)
        draw.text((8, y_base + 6), f"pose=({x_q8:#06x},{y_q8:#06x}) angle={angle}", fill=(215, 222, 235))
        origin_x, origin_y = 16, y_base + 40
        for column, (top, hit, segment) in enumerate(zip(actual[0], expected, segments)):
            x = origin_x + column * 2
            draw.point((x, origin_y + round(hit.top)), fill=(72, 220, 154))
            draw.point((x + 1, origin_y + top), fill=(238, 170, 66))
            if segment != hit.segment:
                draw.line((x, origin_y, x, origin_y + 100), fill=(125, 45, 54))
        draw.text((16, y_base + 132), "green=oracle  amber=engine  red=wrong segment", fill=(135, 145, 163))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=8.0)
    parser.add_argument("--top", type=int, default=64)
    parser.add_argument("--angle-step", type=int, default=4)
    parser.add_argument("--quick", action="store_true", help="scan a small CI-friendly subset")
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "build" / "q14_tail")
    args = parser.parse_args()
    positions = geometry.corpus_positions()
    if args.quick:
        positions = positions[:8]
        args.angle_step = max(args.angle_step, 32)
    report, records = scan(
        threshold_px=args.threshold,
        top_count=args.top,
        angle_step=args.angle_step,
        positions=positions,
    )
    report["configuration"] = {
        "q14_order": engine.Q14_ORDER_ENABLED,
        "folded": engine.FOLDED_COMPOSITOR,
        "level_grid_sha256": hashlib.sha256(engine.make_map()).hexdigest(),
        "benchmark_rom_sha256": hashlib.sha256(engine.make_rom()[0]).hexdigest(),
        "scope": "host floating comparison on this configured level; not an independent-emulator corpus",
    }
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    args.output_prefix.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    write_csv(records, args.output_prefix.with_suffix(".csv"))
    make_sheet(records, args.output_prefix.with_suffix(".png"))
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
