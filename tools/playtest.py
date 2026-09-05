#!/usr/bin/env python3
"""Scriptable, ROM-executing Lupine 3D playtest harness.

Scenarios drive the emitted SM83 program one completed visual update at a
time.  Every captured frame is checked against the independent host geometry
and compositor models before screenshots, a GIF, a contact sheet, and a JSON
telemetry report are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from sm83emu import CGB, parse_symbols  # noqa: E402

BUTTON_BITS = {
    "right": 0x01, "left": 0x02, "up": 0x04, "down": 0x08,
    "a": 0x10, "b": 0x20,
    "select": 0x40, "start": 0x80,
}

WORLD_STATE_FIELDS = {
    "sentinel_state": br.SENTINEL_STATE,
    "sentinel_health": br.SENTINEL_HEALTH,
    "sentinel_visible": br.SENTINEL_VISIBLE,
    "player_health": br.PLAYER_HEALTH,
    "pickup_active": br.PICKUP_ACTIVE,
    "pickup_collected": br.PICKUP_COLLECTED,
    "exit_active": br.EXIT_ACTIVE,
    "level_complete": br.LEVEL_COMPLETE,
}


def door_snapshot(cgb: CGB, offset: int) -> dict[str, int]:
    return {
        door.name: cgb.read8(br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES + offset)
        for index, door in enumerate(br.ACTIVE_LEVEL.doors)
    }


def read_block(cgb: CGB, address: int, count: int) -> bytes:
    return bytes(cgb.read8(address + index) for index in range(count))


def set_test_world_byte(cgb: CGB, address: int, value: int) -> None:
    """Explicit scenario injection into both snapshot and live banks.

    Used only by pose-based diagnostics, never by the controller playthrough.
    Do not copy the whole stale snapshot back over a newer simulated world.
    """
    cgb.write8(address, value)
    if br.FIXED_SIMULATION and 0xD000 <= address < 0xE000:
        cgb.wramx[2][address - 0xD000] = value


def button_mask(names: list[str]) -> int:
    unknown = sorted(set(names) - BUTTON_BITS.keys())
    if unknown:
        raise ValueError(f"unknown buttons: {', '.join(unknown)}")
    return sum(BUTTON_BITS[name] for name in names)


def apply_diagnostic_camera(cgb: CGB, action: dict[str, Any]) -> None:
    """Pose-only injections shared by diagnostic playtests and the profiler."""
    def live16(address: int) -> int:
        if br.FIXED_SIMULATION:
            offset = address - 0xD000
            return int.from_bytes(cgb.wramx[2][offset:offset + 2], "little")
        return cgb.read16(address)
    if action.get("pose_at_drop"):
        for player_address, enemy_address in ((br.PLAYER_XL, br.SENTINEL_XL), (br.PLAYER_YL, br.SENTINEL_YL)):
            value = live16(enemy_address)
            set_test_world_byte(cgb, player_address, value & 255)
            set_test_world_byte(cgb, player_address + 1, value >> 8)
    if "pose" in action:
        x, y, angle = action["pose"]
        for address, value in ((br.PLAYER_XL, x & 255), (br.PLAYER_XH, x >> 8),
                               (br.PLAYER_YL, y & 255), (br.PLAYER_YH, y >> 8), (br.ANGLE, angle)):
            set_test_world_byte(cgb, address, int(value))
    if action.get("aim_at_sentinel"):
        dx = live16(br.SENTINEL_XL) - live16(br.PLAYER_XL)
        dy = live16(br.SENTINEL_YL) - live16(br.PLAYER_YL)
        set_test_world_byte(cgb, br.ANGLE, round(math.atan2(dy, dx) * 128 / math.pi) & 255)


def validate_frame(cgb: CGB) -> dict[str, Any]:
    physical = "refine_full_snapshot" in cgb.symbols
    x_q8 = cgb.read16(br.PLAYER_XL)
    y_q8 = cgb.read16(br.PLAYER_YL)
    angle = cgb.read8(br.ANGLE)
    grid = read_block(cgb, br.MAP, 256)
    door_states = {
        (door.x, door.y): (
            cgb.read8(br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES + br.DOOR_STATE_OFFSET),
            cgb.read8(br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES + br.DOOR_FRACTION_OFFSET),
        )
        for index, door in enumerate(br.ACTIVE_LEVEL.doors)
    }
    if not cgb.read8(br.WORLD_MODE): door_states = {}
    pair = br.reference_adaptive_descriptor_view(x_q8, y_q8, angle, grid, door_states)
    pixel = br.reference_pixel_descriptor_view(x_q8, y_q8, angle, grid, door_states)
    physical_depths = {}
    if physical:
        valid = read_block(cgb,br.PIXEL_DEPTH_VALID,20)
        queried = {x for x in range(160) if valid[x>>3] & (1 << (x&7))}
        pixel,physical_depths = br.reference_refined_descriptor_view(x_q8,y_q8,angle,queried,grid,door_states)

    actual_pair = (
        list(read_block(cgb, br.RAY_TOPS, br.RAYS)),
        list(read_block(cgb, br.RAY_STYLES, br.RAYS)),
        list(read_block(cgb, br.RAY_KEYS, br.RAYS)),
        list(read_block(cgb, br.RAY_ALONG, br.RAYS)),
    )
    actual_pixel = (
        list(read_block(cgb, br.PIXEL_TOPS, br.PHYSICAL_COLUMNS)),
        list(read_block(cgb, br.PIXEL_STYLES, br.PHYSICAL_COLUMNS)),
        list(read_block(cgb, br.PIXEL_KEYS, br.PHYSICAL_COLUMNS)),
        list(read_block(cgb, br.PIXEL_ALONG, br.PHYSICAL_COLUMNS)),
    )
    dynamic, view_map, dynamic_count, overflow = br.reference_compose_view(pixel[0], pixel[1])
    checks = {
        "pair_descriptors_exact": actual_pair == pair[:4],
        "ray_depth_exact": list(read_block(cgb, br.RAY_DEPTH, br.RAYS)) == pair[5],
        "ray_segments_exact": list(read_block(cgb, br.RAY_SEGMENT, br.RAYS)) == pair[6],
        "pixel_descriptors_exact": actual_pixel == pixel[:4],
        "pixel_segments_exact": list(
            read_block(cgb, br.PIXEL_SEGMENT, br.PHYSICAL_COLUMNS)
        ) == pixel[9],
        "adaptive_cast_count_exact": cgb.read8(br.ADAPTIVE_CASTS) == pair[4],
        "edge_recast_count_exact": cgb.read8(br.EDGE_RECASTS) == pixel[5],
        "material_event_count_exact": cgb.read8(br.EVENT_COUNT) == pixel[6],
        "dynamic_count_exact": cgb.read8(br.DYN_COUNT) == dynamic_count,
        "dynamic_tiles_exact": read_block(cgb, br.DYNAMIC_TILES, len(dynamic)) == dynamic,
        "view_map_exact": read_block(cgb, br.VIEW_MAP, len(view_map)) == view_map,
        "no_dynamic_overflow": not overflow and cgb.read8(br.DYN_OVERFLOW) == 0,
        "pixel_surface_profiles_exact": list(read_block(cgb, br.PIXEL_SURFACE, 160)) == pixel[10],
        "surface_attribute_packet_exact": read_block(cgb, br.VIEW_ATTRIBUTES, 384) == br.surface_attributes(pixel[10], cgb.read8(br.CURRENT_PAGE)),
        "input_queue_no_overflow": cgb.read8(br.INPUT_QUEUE_OVERFLOW) == 0,
    }
    page = cgb.read8(br.CURRENT_PAGE)
    if physical:
        checks["queried_physical_depth_exact"] = all(cgb.read8(br.PIXEL_DEPTH+x)==depth for x,depth in physical_depths.items())
        checks["no_unqueried_actor_depth"] = cgb.read8(br.PHYSICAL_DEPTH_MISSING)==0
    offset = 0x1C00 if page else 0x1800
    checks["published_map_exact"] = bytes(cgb.vram[0][offset:offset+384]) == view_map
    checks["published_attributes_exact"] = bytes(cgb.vram[1][offset:offset+384]) == br.surface_attributes(pixel[10], page)
    if cgb.explicit_presentations:
        mask_bytes = cgb.read8(br.MASK_TILE_COUNT) * 16
        obj_page = cgb.read8(br.OBJ_PAGE)
        checks["published_mask_patterns_exact"] = bytes(cgb.vram[obj_page][:mask_bytes]) == read_block(cgb, br.MASK_TILES, mask_bytes)
        checks["published_obj_bank_exact"] = all(
            ((cgb.oam[i*4+3] >> 3) & 1) == obj_page
            for i in range(br.ENTITY_OAM_FIRST, br.ENTITY_OAM_FIRST+cgb.read8(br.SENTINEL_OAM_USED)))
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"frame validation failed: {', '.join(failed)}")
    executed_casts = 0 if cgb.explicit_presentations and cgb.read8(br.FRAME_REUSED) else pixel[4]
    if physical:
        executed_casts = (pixel[4] if cgb.read8(br.GEOMETRY_BACKBONE_RAN) else 0)+cgb.read8(br.PHYSICAL_QUERY_COUNT)
    return {
        "pose": {"x_q8": x_q8, "y_q8": y_q8, "x": x_q8 / 256.0, "y": y_q8 / 256.0, "angle": angle},
        "adaptive_casts": pair[4],
        "edge_recasts": pixel[5],
        "total_casts": pixel[4],
        "material_events": pixel[6],
        "dynamic_tiles": dynamic_count,
        "wall_view_reused": bool(cgb.read8(br.FRAME_REUSED)) if cgb.explicit_presentations else False,
        "executed_casts": executed_casts,
        "checks": checks,
    }


def oam_budget(cgb: CGB) -> dict[str, int]:
    visible = 0
    scanlines = [0] * 144
    height = 16 if cgb.io[0x40] & 4 else 8
    for index in range(40):
        offset = index * 4
        y = cgb.oam[offset] - 16
        x = cgb.oam[offset + 1] - 8
        if y <= -height or y >= 144:
            continue
        if -8 < x < 160:
            visible += 1
        # CGB's ten-object selection tests Y, even for X-offscreen objects.
        for scanline in range(max(0, y), min(144, y + height)):
            scanlines[scanline] += 1
    return {"visible_oam": visible, "max_oam_per_scanline": max(scanlines, default=0)}


def make_contact_sheet(frames: list[tuple[str, Image.Image]], output: Path) -> None:
    scale = 2
    columns = 2
    margin = 12
    label_height = 22
    cell_w = 160 * scale
    cell_h = 144 * scale + label_height
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (
        margin * (columns + 1) + cell_w * columns,
        margin * (rows + 1) + cell_h * rows,
    ), (12, 15, 21))
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(frames):
        column, row = index % columns, index // columns
        x = margin + column * (cell_w + margin)
        y = margin + row * (cell_h + margin)
        sheet.paste(image.resize((cell_w, 144 * scale), Image.Resampling.NEAREST), (x, y))
        draw.text((x, y + 144 * scale + 4), label, fill=(229, 183, 96))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def run_scenario(rom_path: Path, symbols_path: Path, scenario_path: Path,
                 output_dir: Path, record_all: bool = False) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    pixel_oracle: dict[str, str] = {}
    if oracle_name := scenario.get("pixel_oracle"):
        oracle_path = scenario_path.parent / str(oracle_name)
        pixel_oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    symbols = parse_symbols(symbols_path)
    cgb = CGB(rom_path.read_bytes(), symbols)
    cgb.run(until_pc=symbols["main_loop"], max_steps=5_000_000)
    world_mode = str(scenario.get("world_mode", "living")).lower()
    if world_mode not in ("empty", "living"):
        raise ValueError(f"unknown world_mode: {world_mode}")
    set_test_world_byte(cgb, br.WORLD_MODE, br.WORLD_MODE_EMPTY if world_mode == "empty" else br.WORLD_MODE_LIVING)
    output_dir.mkdir(parents=True, exist_ok=True)

    captures: list[tuple[str, Image.Image]] = []
    updates: list[dict[str, Any]] = []
    capture_index = 0

    for action_index, action in enumerate(scenario["actions"]):
        apply_diagnostic_camera(cgb, action)
        buttons = [str(name).lower() for name in action.get("buttons", [])]
        mask = button_mask(buttons)
        cgb.button_provider = lambda _iteration, _swaps, value=mask: value
        action_updates = int(action.get("updates", 1))
        if action_updates < 1:
            raise ValueError(f"action {action_index} has updates < 1")

        for within_action in range(action_updates):
            before_cycles = cgb.cycles
            before_frames = cgb.frame_count
            target_swap = cgb.presentations + 1
            cgb.run(until_presentations=target_swap, max_steps=3_000_000)
            validation = validate_frame(cgb)
            expected_world = {
                str(name): int(value) for name, value in action.get("expect", {}).items()
            } if within_action == action_updates - 1 else {}
            unknown_expectations = sorted(set(expected_world) - WORLD_STATE_FIELDS.keys())
            if unknown_expectations:
                raise ValueError(f"unknown world expectations: {', '.join(unknown_expectations)}")
            actual_world = {
                name: cgb.read8(WORLD_STATE_FIELDS[name]) for name in expected_world
            }
            world_expectations_exact = actual_world == expected_world
            if not world_expectations_exact:
                raise AssertionError(
                    f"world state mismatch: expected {expected_world}, got {actual_world}"
                )
            expected_doors = {
                str(name): int(value)
                for name, value in action.get("expect_doors", {}).items()
            } if within_action == action_updates - 1 else {}
            door_states = door_snapshot(cgb, br.DOOR_STATE_OFFSET)
            door_fractions = door_snapshot(cgb, br.DOOR_FRACTION_OFFSET)
            unknown_doors = sorted(set(expected_doors) - set(door_states))
            if unknown_doors:
                raise ValueError(f"unknown door expectations: {', '.join(unknown_doors)}")
            actual_doors = {name: door_states[name] for name in expected_doors}
            door_expectations_exact = actual_doors == expected_doors
            if not door_expectations_exact:
                raise AssertionError(
                    f"door state mismatch: expected {expected_doors}, got {actual_doors}"
                )
            commit = cgb.commit_events[-1]
            update = {
                "update": len(updates) + 1,
                "action": action_index,
                "buttons": buttons,
                "cycles": cgb.cycles - before_cycles,
                "ppu_frames": cgb.frame_count - before_frames,
                "commit_blocks": commit["blocks"],
                "commit_vblank_safe": commit["vblank_safe"],
                **validation,
                **oam_budget(cgb),
                "world_expectations": expected_world,
                "world_state": actual_world,
                "world_expectations_exact": world_expectations_exact,
                "door_expectations": expected_doors,
                "door_states": door_states,
                "door_fractions": door_fractions,
                "door_expectations_exact": door_expectations_exact,
            }
            updates.append(update)

            should_capture = record_all or (
                within_action == action_updates - 1 and "capture" in action
            )
            if should_capture:
                capture_index += 1
                label = str(action.get("capture", f"update_{len(updates):03d}"))
                image = cgb.render_screen()
                frame_path = output_dir / f"{capture_index:02d}_{label}.png"
                image.save(frame_path)
                update["capture"] = frame_path.name
                update["capture_sha256"] = hashlib.sha256(frame_path.read_bytes()).hexdigest()
                pixel_sha256 = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
                update["capture_pixel_sha256"] = pixel_sha256
                if frame_path.name in pixel_oracle:
                    update["capture_pixels_exact"] = pixel_sha256 == pixel_oracle[frame_path.name]
                captures.append((label, image))

    if not captures:
        image = cgb.render_screen()
        image.save(output_dir / "final.png")
        captures.append(("final", image))

    gif_frames = [image for _, image in captures]
    gif_frames[0].save(
        output_dir / "playtest.gif", save_all=True, append_images=gif_frames[1:],
        duration=180, loop=0, optimize=False,
    )
    make_contact_sheet(captures, output_dir / "contact_sheet.png")

    failures = [
        update["update"] for update in updates
        if (not update["commit_vblank_safe"] or not all(update["checks"].values())
            or update["visible_oam"] > 40 or update["max_oam_per_scanline"] > 10
            or not update["world_expectations_exact"]
            or not update["door_expectations_exact"]
            or update.get("capture_pixels_exact") is False)
    ]
    report = {
        "scenario": scenario.get("name", scenario_path.stem),
        "scenario_file": str(scenario_path),
        "rom": str(rom_path),
        "rom_sha256": hashlib.sha256(rom_path.read_bytes()).hexdigest(),
        "updates": updates,
        "summary": {
            "update_count": len(updates),
            "background_page_swaps": cgb.page_swaps,
            "reused_wall_updates": sum(item["wall_view_reused"] for item in updates),
            "executed_casts": sum(item["executed_casts"] for item in updates),
            "capture_count": len(captures),
            "mean_cycles": sum(item["cycles"] for item in updates) / len(updates),
            "max_cycles": max(item["cycles"] for item in updates),
            "min_updates_per_second": 8_388_608 / max(item["cycles"] for item in updates),
            "max_dynamic_tiles": max(item["dynamic_tiles"] for item in updates),
            "max_total_casts": max(item["total_casts"] for item in updates),
            "max_visible_oam": max(item["visible_oam"] for item in updates),
            "max_oam_per_scanline": max(item["max_oam_per_scanline"] for item in updates),
            "oam_limits_respected": all(
                item["visible_oam"] <= 40 and item["max_oam_per_scanline"] <= 10
                for item in updates
            ),
            "gdma_vblank_violations": cgb.gdma_vblank_violations,
            "pixel_oracle_captures": len(pixel_oracle),
            "pixel_oracle_exact": all(
                update.get("capture_pixels_exact", True) for update in updates
            ),
            "failed_updates": failures,
            "passed": not failures and cgb.gdma_vblank_violations == 0,
        },
        "artifacts": {"gif": "playtest.gif", "contact_sheet": "contact_sheet.png"},
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["summary"]["passed"]:
        raise SystemExit("playtest failed; see report.json")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROOT / "build" / "lupine3d.gb")
    parser.add_argument("--symbols", type=Path, default=ROOT / "build" / "lupine3d.sym")
    parser.add_argument("--scenario", type=Path, default=ROOT / "playtests" / "coherence_tour.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "playtest" / "coherence_tour")
    parser.add_argument("--record-all", action="store_true")
    args = parser.parse_args()
    report = run_scenario(args.rom, args.symbols, args.scenario, args.output_dir, args.record_all)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
