#!/usr/bin/env python3
"""Produce the deterministic current-version release-verification report."""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as v2  # noqa: E402
import build_rom_v1 as v1  # noqa: E402
from sm83emu import CGB, default_input  # noqa: E402

CGB_CLOCK_HZ = 4_194_304
DOTS_PER_LINE = 456
LINES_PER_FRAME = 154
VBLANK_LINES = 10
REFRESH_HZ = CGB_CLOCK_HZ / (DOTS_PER_LINE * LINES_PER_FRAME)
CURRENT_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def header_checksum(rom: bytes) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes) -> int:
    return (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF


def number_stats(values: list[int | float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "max": 0.0}
    return {
        "mean": round(float(statistics.fmean(values)), 3),
        "median": round(float(statistics.median(values)), 3),
        "max": round(float(max(values)), 3),
    }


def run_sample(rom: bytes, symbols: dict[str, int], *, scripted: bool,
               version: str) -> tuple[CGB, dict[str, Any]]:
    cgb = CGB(rom, symbols)
    if scripted:
        cgb.button_provider = default_input
    snap = cgb.run(until_swaps=10, max_steps=20_000_000)
    commits = cgb.commit_events
    commit_blocks = [int(event["blocks"]) for event in commits]
    report: dict[str, Any] = {
        **snap.__dict__,
        "version": version,
        "double_speed": cgb.double_speed,
        "main_iterations": cgb.main_iterations,
        "lcdc": f"0x{cgb.io[0x40]:02X}",
        "estimated_updates_per_second": round(snap.swaps * REFRESH_HZ / snap.frames, 3),
        "cycles_per_completed_update_including_boot": round(snap.cycles / max(1, snap.swaps), 1),
        "gdma_events": len(cgb.gdma_events),
        "commit_events": len(commits),
        "commit_blocks": number_stats(commit_blocks),
        "gdma_vblank_violations": cgb.gdma_vblank_violations,
    }
    if version == CURRENT_VERSION:
        report.update({
            "all_commits_single_frame": all(bool(event["vblank_safe"]) for event in commits),
            "all_commits_two_transfers": all(int(event["event_count"]) == 2 for event in commits),
            "commit_payload_bytes": number_stats([value * 16 for value in commit_blocks]),
            "last_adaptive_casts": cgb.read8(v2.ADAPTIVE_CASTS),
            "last_edge_recasts": cgb.read8(v2.EDGE_RECASTS),
            "last_material_events": cgb.read8(v2.EVENT_COUNT),
            "last_dynamic_tiles": cgb.read8(v2.DYN_COUNT),
            "dynamic_tile_high_water": cgb.read8(v2.DYN_HIGH_WATER),
            "dynamic_tile_overflow": cgb.read8(v2.DYN_OVERFLOW),
            "vblank_interrupts": sum(event["bit"] == 0 for event in cgb.interrupt_events),
            "input_samples": cgb.read8(v2.INPUT_SAMPLE_COUNT),
        })
    return cgb, report


def measure_routines(rom: bytes, symbols: dict[str, int], routines: tuple[str, str],
                     version: str) -> dict[str, Any]:
    cgb = CGB(rom, symbols)
    cgb.run(until_pc=symbols["main_loop"], max_steps=2_000_000)
    result: dict[str, Any] = {"version": version}
    for routine in routines:
        before_cycles, before_steps = cgb.cycles, cgb.steps
        cgb.call_subroutine(routine, max_steps=1_500_000)
        result[routine] = {
            "cycles": cgb.cycles - before_cycles,
            "instructions": cgb.steps - before_steps,
        }
    if version == CURRENT_VERSION:
        result.update({
            "adaptive_casts": cgb.read8(v2.ADAPTIVE_CASTS),
            "dynamic_tiles": cgb.read8(v2.DYN_COUNT),
            "dynamic_tile_overflow": cgb.read8(v2.DYN_OVERFLOW),
        })
    return result


def main() -> None:
    v2_rom, v2_assembler, v2_manifest = v2.make_rom()
    v1_rom, v1_assembler, v1_manifest = v1.make_rom()
    v2.BUILD.mkdir(parents=True, exist_ok=True)
    rom_path = v2.BUILD / "lupine3d.gb"
    rom_path.write_bytes(v2_rom)

    expected_global = (v2_rom[0x014E] << 8) | v2_rom[0x014F]
    research_path = ROOT / "research" / "results" / "geometry_v2_results.json"
    if not research_path.exists():
        raise SystemExit("missing final geometry research; run `make research`")
    research = json.loads(research_path.read_text(encoding="utf-8"))
    v3_research_path = ROOT / "research" / "results" / "rendering_v3_results.json"
    if not v3_research_path.exists():
        raise SystemExit("missing v0.3 rendering research; run `make research-v3`")
    v3_research = json.loads(v3_research_path.read_text(encoding="utf-8"))
    atlas_research_path = ROOT / "research" / "results" / "tile_atlas_v4.json"
    if not atlas_research_path.exists():
        raise SystemExit("missing v0.4 atlas research; run `make research-atlas`")
    atlas_research = json.loads(atlas_research_path.read_text(encoding="utf-8"))
    pareto_path = ROOT / "research" / "results" / "tile_atlas_pareto_v5.json"
    tail_path = ROOT / "research" / "results" / "tail_failures_v4.json"
    entity_atlas_path = ROOT / "research" / "results" / "tile_atlas_entity_80_v6.json"
    if not pareto_path.exists() or not tail_path.exists() or not entity_atlas_path.exists():
        raise SystemExit("missing atlas/tail research; run `make research-atlas-all research-atlas-pareto research-tail`")
    pareto = json.loads(pareto_path.read_text(encoding="utf-8"))
    tail = json.loads(tail_path.read_text(encoding="utf-8"))
    entity_atlas = json.loads(entity_atlas_path.read_text(encoding="utf-8"))
    playtest_path = ROOT / "build" / "playtest" / "coherence_tour" / "report.json"
    if not playtest_path.exists():
        raise SystemExit("missing driven playtest report; run `make playtest`")
    playtest = json.loads(playtest_path.read_text(encoding="utf-8"))
    world_playtest_path = ROOT / "build" / "playtest" / "living_world" / "report.json"
    if not world_playtest_path.exists():
        raise SystemExit("missing Living World playtest report; run `make playtest-world`")
    world_playtest = json.loads(world_playtest_path.read_text(encoding="utf-8"))

    discovered_tests = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    automated_tests = discovered_tests.countTestCases()

    checks = {
        "rom_size_4_mib": len(v2_rom) == v2.ROM_BYTES,
        "cgb_only_flag": v2_rom[0x0143] == 0xC0,
        "mbc5_no_ram_cartridge": v2_rom[0x0147] == 0x19 and v2_rom[0x0149] == 0x00,
        "rom_size_header_4_mib": v2_rom[0x0148] == 0x07,
        "header_checksum": header_checksum(v2_rom) == v2_rom[0x014D],
        "global_checksum": global_checksum(v2_rom) == expected_global,
        "engine_fits_rom": int(v2_manifest["engine_end"]) <= 0x8000,
        "maximum_commit_120_blocks": int(v2_manifest["maximum_commit_blocks"]) <= 120,
        "integer_dda_zero_mismatches": research["integer_dda_identity"]["mismatches"] == 0,
        "adaptive_wall_identity_zero_mismatches": research["adaptive_spans"]["wall_key_mismatches_vs_full_exact"] == 0,
        "adaptive_style_zero_mismatches": research["adaptive_spans"]["style_mismatches_vs_full_exact"] == 0,
        "dynamic_tile_corpus_zero_overflow": research["boundary_tile_renderer"]["overflow_views"] == 0,
        "current_dynamic_tile_stress_zero_overflow": v3_research["current"]["overflow_views"] == 0,
        "v3_mean_geometry_error_improved": v3_research["improvement"]["mean_top_error_reduction_pct"] > 20.0,
        "v3_wrong_segments_improved": v3_research["improvement"]["wrong_segment_reduction_pct"] > 25.0,
        "driven_playtest_passed": bool(playtest["summary"]["passed"]),
        "driven_playtest_zero_unsafe_gdma": playtest["summary"]["gdma_vblank_violations"] == 0,
        "driven_playtest_exact_current_pixels": bool(playtest["summary"]["pixel_oracle_exact"]),
        "driven_playtest_mean_under_1m": float(playtest["summary"]["mean_cycles"]) < 1_000_000,
        "driven_playtest_max_under_1_150k": int(playtest["summary"]["max_cycles"]) < 1_150_000,
        "atlas_exact_signature_entries_255": atlas_research["signature_entries"] == 255,
        "atlas_patterns_fit_vram_121": atlas_research["atlas_patterns"] == 121,
        "entity_atlas_patterns_fit_vram_80": entity_atlas["atlas_patterns"] == 80,
        "entity_atlas_frees_41_ids": entity_atlas["freed_tile_ids"] == 41,
        "entity_atlas_corpus_zero_overflow": entity_atlas["corpus_overflow_views"] == 0,
        "atlas_pareto_full_cache_fastest": min(
            pareto["candidates"], key=lambda item: item["driven_route"]["mean_cycles"]
        )["atlas_patterns"] == 121,
        "tail_corpus_all_large_errors_are_segment_events": (
            tail["tail"]["columns_at_or_above_threshold"] > 0
            and tail["tail"]["tail_columns_with_correct_segment"] == 0
        ),
        "vblank_input_sampling_enabled": bool(v2_manifest["vblank_input_sampling"]),
        "input_edge_latching_enabled": bool(v2_manifest["input_edge_latching"]),
        "interrupts_do_not_mutate_render_pose": not bool(v2_manifest["render_pose_mutated_by_interrupts"]),
        "ray_depth_buffer_80_bytes": int(v2_manifest["ray_depth_buffer_bytes"]) == 80,
        "ray_segment_buffer_80_bytes": int(v2_manifest["ray_segment_buffer_bytes"]) == 80,
        "segment_aware_reconstruction": bool(v2_manifest["segment_aware_reconstruction"]),
        "entity_heavy_profile_active": v2_manifest["vram_profile"] == "entity-heavy",
        "level_v2_safe_spawn_contract": (
            v2_manifest["level_format"] == "lupine-level-v2"
            and int(v2_manifest["safe_spawn_radius_cells"]) >= 5
        ),
        "four_independent_door_records": (
            int(v2_manifest["active_level_doors"]) == 4
            and int(v2_manifest["maximum_level_doors"]) == 4
        ),
        "world_space_exit_beacon": bool(v2_manifest["exit_beacon"]),
        "living_world_playtest_passed": bool(world_playtest["summary"]["passed"]),
        "living_world_oam_total_safe": int(world_playtest["summary"]["max_visible_oam"]) <= 40,
        "living_world_oam_scanline_safe": int(world_playtest["summary"]["max_oam_per_scanline"]) <= 10,
        "living_world_zero_unsafe_gdma": world_playtest["summary"]["gdma_vblank_violations"] == 0,
        "living_world_level_completed": any(
            update.get("world_state", {}).get("level_complete") == 1
            for update in world_playtest["updates"]
        ),
        "living_world_normal_and_exit_doors_completed": (
            any(update.get("door_states", {}).get("start_airlock") == 2 for update in world_playtest["updates"])
            and any(update.get("door_states", {}).get("exit_lock") == 2 for update in world_playtest["updates"])
        ),
        f"automated_test_inventory_{automated_tests}": automated_tests >= 35,
        "material_full_width_contrast_bands_zero": int(v2_manifest["full_width_contrast_bands"]) == 0,
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise SystemExit(f"release validation failed: {failed}")

    v2_stationary_cgb, v2_stationary = run_sample(v2_rom, v2_assembler.labels, scripted=False, version=CURRENT_VERSION)
    v2_action_cgb, v2_action = run_sample(v2_rom, v2_assembler.labels, scripted=True, version=CURRENT_VERSION)
    v1_stationary_cgb, v1_stationary = run_sample(v1_rom, v1_assembler.labels, scripted=False, version="0.1.0")
    v1_action_cgb, v1_action = run_sample(v1_rom, v1_assembler.labels, scripted=True, version="0.1.0")

    runtime_checks = {
        "stationary_no_dynamic_overflow": v2_stationary["dynamic_tile_overflow"] == 0,
        "scripted_no_dynamic_overflow": v2_action["dynamic_tile_overflow"] == 0,
        "stationary_single_vblank_commits": bool(v2_stationary["all_commits_single_frame"]),
        "scripted_single_vblank_commits": bool(v2_action["all_commits_single_frame"]),
        "stationary_two_transfers_per_commit": bool(v2_stationary["all_commits_two_transfers"]),
        "scripted_two_transfers_per_commit": bool(v2_action["all_commits_two_transfers"]),
        "stationary_no_unsafe_gdma": v2_stationary["gdma_vblank_violations"] == 0,
        "scripted_no_unsafe_gdma": v2_action["gdma_vblank_violations"] == 0,
        "stationary_vblank_input_interrupts": v2_stationary["vblank_interrupts"] > 0,
        "scripted_vblank_input_interrupts": v2_action["vblank_interrupts"] > 0,
    }
    checks.update(runtime_checks)
    if not all(runtime_checks.values()):
        failed = ", ".join(name for name, passed in runtime_checks.items() if not passed)
        raise SystemExit(f"runtime validation failed: {failed}")

    v2_action_cgb.render_screen().save(v2.BUILD / "harness_action.png")
    v2_action_cgb.render_screen().save(v2.BUILD / "harness_action_v060.png")
    v1_action_cgb.render_screen().save(v2.BUILD / "harness_action_v010.png")

    v2_routines = measure_routines(v2_rom, v2_assembler.labels, ("cast_all", "render_view"), CURRENT_VERSION)
    v1_routines = measure_routines(v1_rom, v1_assembler.labels, ("cast_all", "render_states"), "0.1.0")

    baseline_rate = float(v1_stationary["estimated_updates_per_second"])
    current_rate = float(v2_stationary["estimated_updates_per_second"])
    report = {
        "project": "Lupine 3D",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "rom": {
            "path": str(rom_path.relative_to(ROOT)),
            "bytes": len(v2_rom),
            "sha256": hashlib.sha256(v2_rom).hexdigest(),
            "header_checksum": f"0x{v2_rom[0x014D]:02X}",
            "global_checksum": f"0x{expected_global:04X}",
            "title": v2_rom[0x0134:0x0143].split(b"\0", 1)[0].decode("ascii"),
            "cgb_flag": f"0x{v2_rom[0x0143]:02X}",
            "cartridge_type": f"0x{v2_rom[0x0147]:02X}",
            "version_byte": f"0x{v2_rom[0x014C]:02X}",
        },
        "checks": checks,
        "automated_tests": automated_tests,
        "architecture": {
            "viewport": v2_manifest["viewport"],
            "geometry_columns": v2_manifest["rays"],
            "physical_columns": v2_manifest["physical_columns"],
            "column_width_pixels": v2_manifest["ray_width_pixels"],
            "ray_traversal": "signed-error exact grid DDA",
            "adaptive_anchor_casts": v2_manifest["adaptive_anchor_casts"],
            "adaptive_validation": v2_manifest["adaptive_validation"],
            "direction_table_entries": v2_manifest["ray_direction_table_entries"],
            "direction_scale": v2_manifest["ray_vector_scale"],
            "projection_fractional_bits": v2_manifest["projection_fractional_bits"],
            "selective_edge_recasts": v2_manifest["selective_edge_recasts"],
            "ray_depth_buffer_bytes": v2_manifest["ray_depth_buffer_bytes"],
            "ray_segment_buffer_bytes": v2_manifest["ray_segment_buffer_bytes"],
            "segment_aware_reconstruction": v2_manifest["segment_aware_reconstruction"],
            "compositor": v2_manifest["renderer"],
            "wall_material_names": v2_manifest["wall_material_names"],
            "wall_pattern_resolution_pairs": v2_manifest["wall_pattern_resolution_pairs"],
            "full_width_contrast_bands": v2_manifest["full_width_contrast_bands"],
            "dynamic_tile_capacity": v2_manifest["dynamic_tile_capacity"],
            "maximum_commit_bytes": v2_manifest["maximum_commit_bytes"],
            "maximum_commit_blocks": v2_manifest["maximum_commit_blocks"],
            "framebuffer_bytes": v2_manifest["framebuffer_bytes"],
            "engine_bytes": v2_manifest["engine_size"],
            "engine_end": f"0x{int(v2_manifest['engine_end']):04X}",
            "hram_hot_state_bytes": v2_manifest["hram_hot_state_bytes"],
            "cartridge": v2_manifest["cartridge_type"],
            "rom_banks": v2_manifest["rom_banks"],
            "projection_lut_bytes": v2_manifest["projection_lut_bytes"],
            "product_lut_bytes": v2_manifest["product_lut_bytes"],
            "vram_profile": v2_manifest["vram_profile"],
            "renderer_atlas_patterns": v2_manifest["renderer_atlas_patterns"],
            "entity_atlas_patterns": v2_manifest["entity_atlas_patterns"],
            "oam_reserved_ui_entries": v2_manifest["oam_reserved_ui_entries"],
            "oam_entity_capacity": v2_manifest["oam_entity_capacity"],
            "level_format": v2_manifest["level_format"],
            "player_collision_radius_q8": v2_manifest["player_collision_radius_q8"],
            "animated_door": v2_manifest["animated_door"],
            "vblank_input_sampling": v2_manifest["vblank_input_sampling"],
            "input_edge_latching": v2_manifest["input_edge_latching"],
            "estimated_maximum_gdma_microseconds": round(int(v2_manifest["maximum_commit_blocks"]) * 8.0, 3),
            "estimated_vblank_microseconds": round(DOTS_PER_LINE * VBLANK_LINES / CGB_CLOCK_HZ * 1_000_000, 3),
        },
        "research_summary": {
            "corpus_views": v3_research["corpus"]["views"],
            "physical_column_samples": v3_research["corpus"]["physical_column_samples"],
            "integer_dda_samples": research["integer_dda_identity"]["quantized_ray_samples"],
            "mean_top_edge_error_reduction_pct_vs_v0_2_2": round(v3_research["improvement"]["mean_top_error_reduction_pct"], 3),
            "wrong_segment_reduction_pct_vs_v0_2_2": round(v3_research["improvement"]["wrong_segment_reduction_pct"], 3),
            "mean_traversal_iteration_reduction_pct": round(research["traversal_work"]["mean_per_ray_iteration_reduction_pct"], 3),
            "mean_total_casts": round(v3_research["current"]["mean_total_casts"], 3),
            "mean_edge_recasts": round(v3_research["current"]["mean_edge_recasts"], 3),
            "mean_dynamic_tiles": round(v3_research["current"]["mean_dynamic_tiles"], 3),
            "exact_atlas_patterns": atlas_research["atlas_patterns"],
            "exact_atlas_signatures": atlas_research["signature_entries"],
            "exact_atlas_coverage_pct": round(atlas_research["coverage_pct"], 3),
            "atlas_pareto_candidates": len(pareto["candidates"]),
            "entity_atlas_patterns": entity_atlas["atlas_patterns"],
            "entity_atlas_freed_tile_ids": entity_atlas["freed_tile_ids"],
            "tail_threshold_px": tail["threshold_px"],
            "tail_columns_at_or_above_threshold": tail["tail"]["columns_at_or_above_threshold"],
            "tail_columns_with_correct_segment": tail["tail"]["tail_columns_with_correct_segment"],
            "full_results": "research/results/rendering_v3_results.json",
        },
        "driven_playtest": playtest["summary"],
        "living_world_playtest": world_playtest["summary"],
        "harness": {
            "scope": "project-specific deterministic SM83/CGB smoke-test harness; not an independent cycle-accurate emulator",
            "refresh_hz_used_for_estimates": round(REFRESH_HZ, 6),
            "current_stationary_10_updates": v2_stationary,
            "current_scripted_10_updates": v2_action,
            "v0_1_stationary_10_updates": v1_stationary,
            "v0_1_scripted_10_updates": v1_action,
            "isolated_routines": {f"v{CURRENT_VERSION}": v2_routines, "v0.1.0": v1_routines},
        },
        "before_after": {
            "horizontal_geometry_columns": {"v0.1.0": 40, f"v{CURRENT_VERSION}": 80},
            "physical_output_columns": {"v0.1.0": 40, f"v{CURRENT_VERSION}": 160},
            "stationary_updates_per_second": {"v0.1.0": baseline_rate, f"v{CURRENT_VERSION}": current_rate},
            "stationary_rate_retained_pct": round(100.0 * current_rate / baseline_rate, 3),
            "engine_bytes": {"v0.1.0": v1_manifest["engine_size"], f"v{CURRENT_VERSION}": v2_manifest["engine_size"]},
            "fixed_framebuffer_bytes": {"v0.1.0": 3840, f"v{CURRENT_VERSION}": 0},
            "commit_vblanks": {"v0.1.0": 2, f"v{CURRENT_VERSION}": 1},
        },
        "physical_hardware_tested": False,
        "hardware_acceptance_document": "docs/HARDWARE_TEST_CHECKLIST.md",
    }
    out = v2.BUILD / "verification_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
