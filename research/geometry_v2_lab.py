#!/usr/bin/env python3
"""Final geometry and bandwidth research lab for Lupine 3D v0.2.0.

The lab compares three renderer paths over a deterministic corpus:

* v0.1.0: forty quarter-tile marcher rays, four pixels per ray;
* v0.2.0 exact: eighty signed-error DDA rays, two pixels per ray;
* v0.2.0 adaptive: forty-one mandatory anchors plus validated midpoint casts.

A floating camera-plane DDA at every physical viewport column is the visual
reference.  The integer DDA identity check is separate and uses the exact same
quantized vectors as the ROM.  Results are mathematical / harness evidence,
not a substitute for timing the ROM on original hardware.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom_v2 as v2  # noqa: E402
import build_rom_v1 as v1  # noqa: E402

VIEW_W, VIEW_H = v2.VIEWPORT
FOV_DEG = v2.FOV_DEGREES
GRID_BYTES = list(v2.make_map())
GRID = [GRID_BYTES[y * 16:(y + 1) * 16] for y in range(16)]
OUT_DIR = ROOT / "research" / "results"


@dataclass(frozen=True)
class Hit:
    cell_x: int
    cell_y: int
    axis: int                 # 0 = crossed X boundary, 1 = crossed Y boundary
    distance_q8: int
    material: int
    crossings: int
    segment: str


@dataclass(frozen=True)
class FloatHit:
    top: float
    axis: int
    material: int
    cell_x: int
    cell_y: int
    segment: str


def signed8(value: int) -> int:
    return value - 256 if value & 0x80 else value


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))])


def stats(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "mean": float(statistics.fmean(values)),
        "median": float(statistics.median(values)),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": float(max(values)),
    }


def build_face_segments() -> dict[tuple[int, int, str], str]:
    """Assign each exposed cell face to a maximal collinear material segment."""
    faces: dict[tuple[int, int, str], str] = {}

    for side, dx in (("W", -1), ("E", 1)):
        for boundary in range(17):
            cell_x = boundary if side == "W" else boundary - 1
            y = 0
            while y < 16:
                if not 0 <= cell_x < 16:
                    y += 1
                    continue
                neighbor_x = cell_x + dx
                material = GRID[y][cell_x]
                exposed = material != 0 and (not 0 <= neighbor_x < 16 or GRID[y][neighbor_x] == 0)
                if not exposed:
                    y += 1
                    continue
                start = y
                while y + 1 < 16:
                    yy = y + 1
                    m2 = GRID[yy][cell_x]
                    exposed2 = m2 == material and (not 0 <= neighbor_x < 16 or GRID[yy][neighbor_x] == 0)
                    if not exposed2:
                        break
                    y += 1
                segment = f"V:{boundary}:{start}-{y}:m{material}:{side}"
                for yy in range(start, y + 1):
                    faces[(cell_x, yy, side)] = segment
                y += 1

    for side, dy in (("N", -1), ("S", 1)):
        for boundary in range(17):
            cell_y = boundary if side == "N" else boundary - 1
            x = 0
            while x < 16:
                if not 0 <= cell_y < 16:
                    x += 1
                    continue
                neighbor_y = cell_y + dy
                material = GRID[cell_y][x]
                exposed = material != 0 and (not 0 <= neighbor_y < 16 or GRID[neighbor_y][x] == 0)
                if not exposed:
                    x += 1
                    continue
                start = x
                while x + 1 < 16:
                    xx = x + 1
                    m2 = GRID[cell_y][xx]
                    exposed2 = m2 == material and (not 0 <= neighbor_y < 16 or GRID[neighbor_y][xx] == 0)
                    if not exposed2:
                        break
                    x += 1
                segment = f"H:{boundary}:{start}-{x}:m{material}:{side}"
                for xx in range(start, x + 1):
                    faces[(xx, cell_y, side)] = segment
                x += 1
    return faces


FACE_SEGMENTS = build_face_segments()


def segment_for(cell_x: int, cell_y: int, axis: int, dx: float, dy: float, material: int) -> str:
    if axis == 0:
        side = "W" if dx > 0 else "E"
    else:
        side = "N" if dy > 0 else "S"
    return FACE_SEGMENTS.get((cell_x, cell_y, side), f"cell:{cell_x},{cell_y}:{side}:m{material}")


@lru_cache(maxsize=None)
def float_ray_setup(player_angle: int, screen_x: float) -> tuple[float, float, float, float, int, int]:
    """Cache the camera ray because every corpus position reuses the same 8×160 rays."""
    angle = player_angle * math.tau / 256.0
    dir_x, dir_y = math.cos(angle), math.sin(angle)
    plane_scale = math.tan(math.radians(FOV_DEG * 0.5))
    camera_x = 2.0 * screen_x / VIEW_W - 1.0
    ray_x = dir_x - dir_y * plane_scale * camera_x
    ray_y = dir_y + dir_x * plane_scale * camera_x
    delta_x = abs(1.0 / ray_x) if abs(ray_x) > 1e-12 else 1e30
    delta_y = abs(1.0 / ray_y) if abs(ray_y) > 1e-12 else 1e30
    return ray_x, ray_y, delta_x, delta_y, (-1 if ray_x < 0 else 1), (-1 if ray_y < 0 else 1)


def float_camera_hit(px: float, py: float, player_angle: int, screen_x: float, *, horizon: float = 48.0) -> FloatHit:
    """Floating camera-plane DDA reference at one physical column center."""
    ray_x, ray_y, delta_x, delta_y, step_x, step_y = float_ray_setup(player_angle, screen_x)
    map_x, map_y = int(math.floor(px)), int(math.floor(py))
    if step_x < 0:
        side_x = (px - map_x) * delta_x
    else:
        side_x = (map_x + 1.0 - px) * delta_x
    if step_y < 0:
        side_y = (py - map_y) * delta_y
    else:
        side_y = (map_y + 1.0 - py) * delta_y

    for _ in range(64):
        if side_x <= side_y:
            distance = side_x
            side_x += delta_x
            map_x += step_x
            axis = 0
        else:
            distance = side_y
            side_y += delta_y
            map_y += step_y
            axis = 1
        material = GRID[map_y][map_x]
        if material:
            half = max(2.0, min(horizon, 30.0 / max(distance, 1e-12)))
            segment = segment_for(map_x, map_y, axis, ray_x, ray_y, material)
            return FloatHit(horizon - half, axis, material, map_x, map_y, segment)
    raise RuntimeError("floating DDA escaped the enclosed map")


def exact_cross_product(pxq: int, pyq: int, dx: int, dy: int) -> Hit:
    """Exact traversal ordering for one quantized ray vector."""
    map_x, map_y = pxq >> 8, pyq >> 8
    frac_x, frac_y = pxq & 0xFF, pyq & 0xFF
    abs_x, abs_y = abs(dx), abs(dy)
    step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    next_x = (256 - frac_x if dx > 0 else frac_x) if dx else 0x7FFF
    next_y = (256 - frac_y if dy > 0 else frac_y) if dy else 0x7FFF
    for crossings in range(1, 33):
        choose_x = dx != 0 and (dy == 0 or next_x * abs_y <= next_y * abs_x)
        if choose_x:
            map_x += step_x
            axis, distance = 0, next_x
            next_x += 256
        else:
            map_y += step_y
            axis, distance = 1, next_y
            next_y += 256
        material = GRID[map_y][map_x]
        if material:
            return Hit(map_x, map_y, axis, distance, material, crossings,
                       segment_for(map_x, map_y, axis, dx, dy, material))
    raise RuntimeError("exact quantized ray did not hit")


def signed_error_dda(pxq: int, pyq: int, dx: int, dy: int) -> Hit:
    """Host mirror of the ROM's signed-error cell-boundary traversal."""
    map_x, map_y = pxq >> 8, pyq >> 8
    frac_x, frac_y = pxq & 0xFF, pyq & 0xFF
    abs_x, abs_y = abs(dx), abs(dy)
    step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    next_x = (256 - frac_x if dx > 0 else frac_x) if dx else 0x7FFF
    next_y = (256 - frac_y if dy > 0 else frac_y) if dy else 0x7FFF
    if dx == 0:
        error = 0x7FFF
    elif dy == 0:
        error = -0x8000
    else:
        error = next_x * abs_y - next_y * abs_x

    for crossings in range(1, 33):
        choose_x = dx != 0 and (dy == 0 or error <= 0)
        if choose_x:
            map_x += step_x
            axis, distance = 0, next_x
        else:
            map_y += step_y
            axis, distance = 1, next_y
        material = GRID[map_y][map_x]
        if material:
            return Hit(map_x, map_y, axis, distance, material, crossings,
                       segment_for(map_x, map_y, axis, dx, dy, material))
        if choose_x:
            next_x += 256
            error += 256 * abs_y
        else:
            next_y += 256
            error -= 256 * abs_x
    raise RuntimeError("signed-error ray did not hit")


def step_entry_axis(prev_x: int, prev_y: int, cur_x: int, cur_y: int,
                    cell_x: int, cell_y: int) -> int:
    """Return the first grid face crossed by the marcher's final line segment."""
    dx, dy = cur_x - prev_x, cur_y - prev_y
    candidates: list[tuple[float, int]] = []
    if dx > 0:
        t = ((cell_x << 8) - prev_x) / dx
        y = prev_y + t * dy
        if 0.0 <= t <= 1.0 and (cell_y << 8) - 1 <= y <= ((cell_y + 1) << 8) + 1:
            candidates.append((t, 0))
    elif dx < 0:
        t = (((cell_x + 1) << 8) - prev_x) / dx
        y = prev_y + t * dy
        if 0.0 <= t <= 1.0 and (cell_y << 8) - 1 <= y <= ((cell_y + 1) << 8) + 1:
            candidates.append((t, 0))
    if dy > 0:
        t = ((cell_y << 8) - prev_y) / dy
        x = prev_x + t * dx
        if 0.0 <= t <= 1.0 and (cell_x << 8) - 1 <= x <= ((cell_x + 1) << 8) + 1:
            candidates.append((t, 1))
    elif dy < 0:
        t = (((cell_y + 1) << 8) - prev_y) / dy
        x = prev_x + t * dx
        if 0.0 <= t <= 1.0 and (cell_x << 8) - 1 <= x <= ((cell_x + 1) << 8) + 1:
            candidates.append((t, 1))
    if candidates:
        return min(candidates)[1]
    return 0 if abs(dx) >= abs(dy) else 1


V1_STEP_DX, V1_STEP_DY, _, _, V1_RAY_BLOB = v1.make_ray_tables()
V1_OFFSETS = [signed8(x) for x in V1_RAY_BLOB[:40]]
V1_HEIGHT_TABLES = V1_RAY_BLOB[40:]
V1_HEIGHT_LEVELS = [4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 56, 64, 72, 80, 96]


def v1_view(pxq: int, pyq: int, player_angle: int) -> tuple[list[int], list[str], list[int], list[int]]:
    """Reproduce v0.1.0's forty quarter-step ray descriptors."""
    tops: list[int] = []
    segments: list[str] = []
    materials: list[int] = []
    steps_out: list[int] = []
    for ray_index, offset in enumerate(V1_OFFSETS):
        angle = (player_angle + offset) & 0xFF
        dx, dy = signed8(V1_STEP_DX[angle]), signed8(V1_STEP_DY[angle])
        x, y = pxq, pyq
        for steps in range(1, 128):
            prev_x, prev_y = x, y
            x += dx
            y += dy
            cell_x, cell_y = x >> 8, y >> 8
            material = GRID[cell_y][cell_x]
            if material:
                axis = step_entry_axis(prev_x, prev_y, x, y, cell_x, cell_y)
                segment = segment_for(cell_x, cell_y, axis, dx, dy, material)
                level = V1_HEIGHT_TABLES[ray_index * 128 + steps]
                height = V1_HEIGHT_LEVELS[level]
                tops.append((VIEW_H - height) // 2)
                segments.append(segment)
                materials.append(material)
                steps_out.append(steps)
                break
        else:
            raise RuntimeError("v0.1 marcher did not hit")
    return tops, segments, materials, steps_out


def v2_segments(keys: Sequence[int], alongs: Sequence[int], player_angle: int) -> list[str]:
    tables = v2.make_tables()
    offsets = [int.from_bytes(tables["ray_offsets"][i:i + 2], "little", signed=True)
               for i in range(0, v2.RAYS * 2, 2)]
    dx_table = [signed8(value) for value in tables["ray_dx"]]
    dy_table = [signed8(value) for value in tables["ray_dy"]]
    result: list[str] = []
    for index, (key, along) in enumerate(zip(keys, alongs)):
        axis = (key >> 7) & 1
        material = (key >> 5) & 3
        plane = key & 31
        ray_index = ((player_angle << 2) + offsets[index]) & 0x3FF
        dx, dy = dx_table[ray_index], dy_table[ray_index]
        if axis == 0:
            cell_x = plane if dx > 0 else plane - 1
            cell_y = along
        else:
            cell_x = along
            cell_y = plane if dy > 0 else plane - 1
        result.append(segment_for(cell_x, cell_y, axis, dx, dy, material))
    return result


def descriptor_from_hit(hit: Hit, dx: int, dy: int, correction: int,
                        projection: bytes) -> tuple[int, int, int, int, str]:
    component = abs(dx) if hit.axis == 0 else abs(dy)
    d16 = min(255, (hit.distance_q8 + 8) >> 4)
    perp16 = 255 if component == 0 else min(255, (d16 * correction + component // 2) // component)
    top = 48 - projection[perp16]
    style = 4 if hit.material == 3 else (2 + hit.axis if hit.material == 2 else hit.axis)
    if hit.axis == 0:
        plane = hit.cell_x + (1 if dx < 0 else 0)
        along = hit.cell_y
    else:
        plane = hit.cell_y + (1 if dy < 0 else 0)
        along = hit.cell_x
    key = (hit.axis << 7) | ((hit.material & 3) << 5) | (plane & 31)
    return top, style, key, along & 0xFF, hit.segment


def adaptive_from_full(tops: Sequence[int], styles: Sequence[int], keys: Sequence[int],
                       alongs: Sequence[int]) -> tuple[list[int], list[int], list[int], list[int], int]:
    at = [0] * v2.RAYS
    ast = [0] * v2.RAYS
    ak = [0] * v2.RAYS
    aa = [0] * v2.RAYS
    casts = 0
    for i in range(0, v2.RAYS, 2):
        at[i], ast[i], ak[i], aa[i] = tops[i], styles[i], keys[i], alongs[i]
        casts += 1
    at[79], ast[79], ak[79], aa[79] = tops[79], styles[79], keys[79], alongs[79]
    casts += 1
    for i in range(1, 78, 2):
        if (
            ak[i - 1] == ak[i + 1]
            and abs(aa[i - 1] - aa[i + 1]) <= 1
            and abs(at[i - 1] - at[i + 1]) <= 2
        ):
            at[i] = (at[i - 1] + at[i + 1] + 1) // 2
            ast[i], ak[i], aa[i] = ast[i - 1], ak[i - 1], aa[i - 1]
        else:
            at[i], ast[i], ak[i], aa[i] = tops[i], styles[i], keys[i], alongs[i]
            casts += 1
    return at, ast, ak, aa, casts


def corpus_positions() -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for y in range(1, 15):
        for x in range(1, 15):
            if GRID[y][x] == 0:
                for frac_x, frac_y in ((0x40, 0x40), (0x80, 0x80), (0xC0, 0x40)):
                    positions.append(((x << 8) | frac_x, (y << 8) | frac_y))
    return positions


def expand(values: Sequence[object], width: int) -> list[object]:
    return [value for value in values for _ in range(width)]


def render_geometry(tops: Sequence[float], materials: Sequence[int], axes: Sequence[int]) -> Image.Image:
    palette = {
        (1, 0): (194, 137, 63), (1, 1): (113, 76, 48),
        (2, 0): (93, 178, 190), (2, 1): (54, 105, 126),
        (3, 0): (186, 72, 58), (3, 1): (132, 45, 45),
    }
    image = Image.new("RGB", (VIEW_W, VIEW_H), (18, 28, 52))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, VIEW_H // 2, VIEW_W - 1, VIEW_H - 1), fill=(60, 61, 67))
    for x, (top, material, axis) in enumerate(zip(tops, materials, axes)):
        y0 = max(0, min(VIEW_H - 1, int(round(top))))
        y1 = VIEW_H - 1 - y0
        draw.line((x, y0, x, y1), fill=palette.get((material, axis), (180, 150, 80)))
    return image


def make_comparison_image(path: Path) -> None:
    scenes = [(0x0180, 0x0180, 0), (0x0780, 0x0780, 32), (0x0B40, 0x0D90, 196)]
    labels = ("v0.1 quarter-step / 40 rays", "v0.2 adaptive DDA / 80 columns", "160-column float reference")
    label_h = 18
    canvas = Image.new("RGB", (VIEW_W * 3, (VIEW_H + label_h) * len(scenes)), (12, 12, 14))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for row, (pxq, pyq, angle) in enumerate(scenes):
        v1_tops, v1_segments, v1_materials, _ = v1_view(pxq, pyq, angle)
        v1_tops_x = [float(x) for x in expand(v1_tops, 4)]
        v1_materials_x = [int(x) for x in expand(v1_materials, 4)]
        # Recover an orientation bit from the segment prefix.
        v1_axes = [0 if str(seg).startswith("V:") else 1 for seg in expand(v1_segments, 4)]

        full_tops, full_styles, full_keys, full_alongs = v2.reference_full_descriptor_view(pxq, pyq, angle)
        at, ast, ak, aa, _ = adaptive_from_full(full_tops, full_styles, full_keys, full_alongs)
        v2_tops_x = [float(x) for x in expand(at, 2)]
        v2_materials_x = [((int(k) >> 5) & 3) for k in expand(ak, 2)]
        v2_axes = [((int(k) >> 7) & 1) for k in expand(ak, 2)]

        exact = [float_camera_hit(pxq / 256.0, pyq / 256.0, angle, x + 0.5) for x in range(VIEW_W)]
        exact_tops = [h.top for h in exact]
        exact_materials = [h.material for h in exact]
        exact_axes = [h.axis for h in exact]
        images = (
            render_geometry(v1_tops_x, v1_materials_x, v1_axes),
            render_geometry(v2_tops_x, v2_materials_x, v2_axes),
            render_geometry(exact_tops, exact_materials, exact_axes),
        )
        y = row * (VIEW_H + label_h)
        for col, (label, image) in enumerate(zip(labels, images)):
            x = col * VIEW_W
            canvas.paste(image, (x, y + label_h))
            draw.text((x + 3, y + 4), label, font=font, fill=(235, 235, 235))
    canvas.resize((canvas.width * 2, canvas.height * 2), Image.Resampling.NEAREST).save(path)


def run() -> dict[str, object]:
    positions = corpus_positions()
    # Eight evenly spaced headings cover every cardinal and diagonal viewing
    # family while keeping the independent 160-column floating reference
    # practical in routine release verification. ROM-vs-host tests separately
    # exercise non-cardinal angle values.
    angles = range(0, 256, 32)
    tables = v2.make_tables()
    offsets_q10 = [int.from_bytes(tables["ray_offsets"][i:i + 2], "little", signed=True)
                   for i in range(0, v2.RAYS * 2, 2)]
    ray_dx = [signed8(value) for value in tables["ray_dx"]]
    ray_dy = [signed8(value) for value in tables["ray_dy"]]

    dda_mismatches = 0
    dda_first: list[dict[str, object]] = []
    baseline_errors: list[float] = []
    v2_exact_errors: list[float] = []
    v2_adaptive_errors: list[float] = []
    adaptive_vs_full_errors: list[float] = []
    baseline_segment_wrong = 0
    v2_exact_segment_wrong = 0
    v2_adaptive_segment_wrong = 0
    baseline_material_wrong = 0
    v2_exact_material_wrong = 0
    v2_adaptive_material_wrong = 0
    adaptive_key_wrong = 0
    adaptive_style_wrong = 0
    baseline_steps: list[float] = []
    dda_crossings: list[float] = []
    adaptive_casts: list[float] = []
    dynamic_tiles: list[float] = []
    commit_bytes: list[float] = []
    overflow_views = 0
    view_count = 0
    pixel_samples = 0

    for pxq, pyq in positions:
        for player_angle in angles:
            # Independent integer traversal identity for every v0.2 ray.
            for off in offsets_q10:
                direction = ((player_angle << 2) + off) & 0x3FF
                dx, dy = ray_dx[direction], ray_dy[direction]
                exact_q = exact_cross_product(pxq, pyq, dx, dy)
                signed_q = signed_error_dda(pxq, pyq, dx, dy)
                dda_crossings.append(float(signed_q.crossings))
                if exact_q != signed_q:
                    dda_mismatches += 1
                    if len(dda_first) < 10:
                        dda_first.append({
                            "pose": [pxq, pyq, player_angle], "offset_q10": off,
                            "vector": [dx, dy], "exact": exact_q.__dict__, "signed": signed_q.__dict__,
                        })

            v1_tops, v1_segments, v1_materials, v1_steps = v1_view(pxq, pyq, player_angle)
            baseline_steps.extend(float(x) for x in v1_steps)
            b_tops = [float(x) for x in expand(v1_tops, 4)]
            b_segments = [str(x) for x in expand(v1_segments, 4)]
            b_materials = [int(x) for x in expand(v1_materials, 4)]

            ft: list[int] = []
            fs: list[int] = []
            fk: list[int] = []
            fa: list[int] = []
            full_segments: list[str] = []
            for ray_index, off in enumerate(offsets_q10):
                direction = ((player_angle << 2) + off) & 0x3FF
                dx, dy = ray_dx[direction], ray_dy[direction]
                hit = signed_error_dda(pxq, pyq, dx, dy)
                top, style, key, along, segment = descriptor_from_hit(
                    hit, dx, dy, tables["ray_corrections"][ray_index], tables["projection_half"]
                )
                ft.append(top); fs.append(style); fk.append(key); fa.append(along); full_segments.append(segment)
            at, ast, ak, aa, cast_count = adaptive_from_full(ft, fs, fk, fa)
            adaptive_segments = v2_segments(ak, aa, player_angle)
            e_tops = [float(x) for x in expand(ft, 2)]
            e_segments = [str(x) for x in expand(full_segments, 2)]
            e_materials = [((int(k) >> 5) & 3) for k in expand(fk, 2)]
            a_tops = [float(x) for x in expand(at, 2)]
            a_segments = [str(x) for x in expand(adaptive_segments, 2)]
            a_materials = [((int(k) >> 5) & 3) for k in expand(ak, 2)]

            reference = [float_camera_hit(pxq / 256.0, pyq / 256.0, player_angle, x + 0.5)
                         for x in range(VIEW_W)]
            r_tops = [h.top for h in reference]
            r_segments = [h.segment for h in reference]
            r_materials = [h.material for h in reference]

            baseline_errors.extend(abs(a - b) for a, b in zip(b_tops, r_tops))
            v2_exact_errors.extend(abs(a - b) for a, b in zip(e_tops, r_tops))
            v2_adaptive_errors.extend(abs(a - b) for a, b in zip(a_tops, r_tops))
            adaptive_vs_full_errors.extend(abs(a - b) for a, b in zip(at, ft))
            baseline_segment_wrong += sum(a != b for a, b in zip(b_segments, r_segments))
            v2_exact_segment_wrong += sum(a != b for a, b in zip(e_segments, r_segments))
            v2_adaptive_segment_wrong += sum(a != b for a, b in zip(a_segments, r_segments))
            baseline_material_wrong += sum(a != b for a, b in zip(b_materials, r_materials))
            v2_exact_material_wrong += sum(a != b for a, b in zip(e_materials, r_materials))
            v2_adaptive_material_wrong += sum(a != b for a, b in zip(a_materials, r_materials))
            adaptive_key_wrong += sum(a != b for a, b in zip(ak, fk))
            adaptive_style_wrong += sum(a != b for a, b in zip(ast, fs))
            adaptive_casts.append(float(cast_count))
            _, _, dyn_count, overflow = v2.reference_compose_view(at, ast)
            dynamic_tiles.append(float(dyn_count))
            commit_bytes.append(float(dyn_count * 16 + 384))
            overflow_views += int(overflow)
            view_count += 1
            pixel_samples += VIEW_W

    def method_row(name: str, errors: Sequence[float], segment_wrong: int,
                   material_wrong: int) -> dict[str, object]:
        return {
            "method": name,
            "top_edge_abs_error_px": stats(errors),
            "wrong_wall_segment_pct": 100.0 * segment_wrong / pixel_samples,
            "wrong_material_pct": 100.0 * material_wrong / pixel_samples,
            "physical_column_samples": pixel_samples,
        }

    baseline_mean = statistics.fmean(baseline_errors)
    adaptive_mean = statistics.fmean(v2_adaptive_errors)
    results: dict[str, object] = {
        "configuration": {
            "views": view_count,
            "positions": len(positions),
            "angles_per_position": len(list(angles)),
            "physical_column_reference_rays": pixel_samples,
            "map_size": [16, 16],
            "viewport": [VIEW_W, VIEW_H],
            "fov_degrees": FOV_DEG,
        },
        "integer_dda_identity": {
            "quantized_ray_samples": view_count * v2.RAYS,
            "mismatches": dda_mismatches,
            "first_mismatches": dda_first,
            "grid_crossings": stats(dda_crossings),
        },
        "geometry_accuracy": [
            method_row("v0.1.0 quarter-step, 40 rays / 4 px", baseline_errors,
                       baseline_segment_wrong, baseline_material_wrong),
            method_row("v0.2.0 full exact DDA, 80 rays / 2 px", v2_exact_errors,
                       v2_exact_segment_wrong, v2_exact_material_wrong),
            method_row("v0.2.0 validated adaptive DDA, 80 columns", v2_adaptive_errors,
                       v2_adaptive_segment_wrong, v2_adaptive_material_wrong),
        ],
        "improvement_vs_v0_1": {
            "mean_top_edge_error_reduction_pct": 100.0 * (1.0 - adaptive_mean / baseline_mean),
            "wrong_segment_reduction_pct": 100.0 * (1.0 - v2_adaptive_segment_wrong / baseline_segment_wrong)
            if baseline_segment_wrong else 0.0,
            "wrong_material_reduction_pct": 100.0 * (1.0 - v2_adaptive_material_wrong / baseline_material_wrong)
            if baseline_material_wrong else 0.0,
            "horizontal_geometry_columns": {"v0.1.0": 40, "v0.2.0": 80},
        },
        "traversal_work": {
            "v0_1_quarter_tile_steps_per_ray": stats(baseline_steps),
            "v0_2_grid_crossings_per_exact_cast": stats(dda_crossings),
            "mean_per_ray_iteration_reduction_pct": 100.0 * (
                1.0 - statistics.fmean(dda_crossings) / statistics.fmean(baseline_steps)
            ),
        },
        "adaptive_spans": {
            "mandatory_anchor_casts": 41,
            "maximum_anchor_top_delta_for_interpolation": 2,
            "actual_casts_per_view": stats(adaptive_casts),
            "mean_rays_avoided_vs_full_80": 80.0 - statistics.fmean(adaptive_casts),
            "wall_key_mismatches_vs_full_exact": adaptive_key_wrong,
            "style_mismatches_vs_full_exact": adaptive_style_wrong,
            "top_edge_abs_error_px_vs_full_exact": stats(adaptive_vs_full_errors),
        },
        "boundary_tile_renderer": {
            "dynamic_tile_capacity": v2.DYNAMIC_TILE_CAPACITY,
            "dynamic_tiles_per_view": stats(dynamic_tiles),
            "commit_bytes_per_view": stats(commit_bytes),
            "overflow_views": overflow_views,
            "maximum_commit_bytes": v2.DYNAMIC_TILE_CAPACITY * 16 + 384,
            "v0_1_framebuffer_bytes": 3840,
            "mean_vram_payload_reduction_pct": 100.0 * (
                1.0 - statistics.fmean(commit_bytes) / 3840.0
            ),
        },
    }
    return results


def write_csv(results: dict[str, object], path: Path) -> None:
    rows = []
    for method in results["geometry_accuracy"]:  # type: ignore[index]
        error = method["top_edge_abs_error_px"]
        rows.append({
            "method": method["method"],
            "top_mae_px": error["mean"],
            "top_p95_px": error["p95"],
            "top_p99_px": error["p99"],
            "top_max_px": error["max"],
            "wrong_wall_segment_pct": method["wrong_wall_segment_pct"],
            "wrong_material_pct": method["wrong_material_pct"],
            "physical_column_samples": method["physical_column_samples"],
        })
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = run()
    json_path = OUT_DIR / "geometry_v2_results.json"
    csv_path = OUT_DIR / "geometry_v2_accuracy.csv"
    image_path = OUT_DIR / "geometry_v2_comparison.png"
    json_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    write_csv(results, csv_path)
    make_comparison_image(image_path)
    print(json.dumps(results, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {image_path}")
    if results["integer_dda_identity"]["mismatches"]:  # type: ignore[index]
        raise SystemExit("signed-error DDA identity check failed")
    if results["adaptive_spans"]["wall_key_mismatches_vs_full_exact"]:  # type: ignore[index]
        raise SystemExit("adaptive span wall identity check failed")
    if results["boundary_tile_renderer"]["overflow_views"]:  # type: ignore[index]
        raise SystemExit("dynamic tile capacity overflowed in research corpus")


if __name__ == "__main__":
    main()
