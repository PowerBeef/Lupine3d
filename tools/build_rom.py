#!/usr/bin/env python3
"""Compatibility facade and ROM linker for Lupine 3D.

Implementation details live in ``lupine3d_v4``.  Tests and research tools may
continue importing this module as ``build_rom`` without API churn.
"""
from __future__ import annotations

import hashlib
import json

from lupine3d_v4.layout import *  # noqa: F401,F403
from lupine3d_v4.resources import *  # noqa: F401,F403
from lupine3d_v4.reference import *  # noqa: F401,F403
from lupine3d_v4.emitter import *  # noqa: F401,F403
from lupine3d_v4.living_world import *  # noqa: F401,F403
# living_world re-exports the compatibility layout namespace. Reassert the
# current art generators after that import so the frozen v0.1 helpers cannot
# shadow the active industrial-gothic UI and weapon assets.
from lupine3d_v4.resources import make_ui_tiles, make_weapon_tiles  # noqa: E402

def build_engine() -> tuple[bytes, Assembler, dict[str, object]]:
    tables = make_tables()
    a = Assembler(origin=0x0150, optimize_high_page=True)
    a.label("start")
    a.di(); a.ld_rr_nn("sp", 0xDFFF); a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
    a.xor_r("a"); a.ld_abs_a(0xFFFF); a.ld_abs_a(0xFF0F)
    a.ld_r_n("a", 1); a.ldh_n_a(KEY1); a.stop()
    a.label("startup_wait_vblank")
    a.ldh_a_n(LY); a.cp_n(144); a.jr("startup_wait_vblank", "c")
    a.xor_r("a"); a.ldh_n_a(LCDC); a.ldh_n_a(SCX); a.ldh_n_a(SCY)
    a.call("load_level")
    a.xor_r("a"); a.ld_abs_a(BUTTONS); a.ld_abs_a(PREV_BUTTONS); a.ld_abs_a(FLASH); a.ld_abs_a(CURRENT_PAGE); a.ld_abs_a(DYN_HIGH_WATER)
    a.ld_abs_a(INPUT_LAST_RAW); a.ld_abs_a(INPUT_EDGE_LATCH); a.ld_abs_a(INPUT_SAMPLE_COUNT)
    a.call("init_palettes"); a.call("init_vram"); a.call("update_hud_tiles"); a.call("init_oam"); a.call("init_audio")
    a.call("cast_all"); a.call("render_view"); a.call("render_entities"); a.call("populate_reprojection_guards"); a.call("upload_initial_both_pages")
    a.ld_r_n("a", 0x93); a.ldh_n_a(LCDC)
    a.xor_r("a"); a.ld_abs_a(0xFF0F)
    if ENABLE_MICRO_REPROJECTION:
        a.ld_r_n("a", 96); a.ldh_n_a(LYC); a.ld_r_n("a", 0x40); a.ldh_n_a(STAT)
        a.ld_r_n("a", 3); a.ld_abs_a(0xFFFF)
    else:
        a.ld_r_n("a", 1); a.ld_abs_a(0xFFFF)
    a.ei(); a.nop()
    a.label("main_loop")
    a.call("update_input"); a.call("update_world"); a.call("cast_all"); a.call("render_view"); a.call("render_entities"); a.call("populate_reprojection_guards"); a.call("upload_hidden_page"); a.jp("main_loop")

    # Runtime routines.
    v1.emit_copy_routine(a); v1.emit_wait_vblank(a); emit_palette_init(a); emit_hud_system(a)
    emit_level_loader(a); emit_vram_init(a); emit_oam_system(a); emit_door_system(a); v1.emit_audio(a); emit_dma(a); emit_input_system(a)
    # Legacy quarter-step helpers are retained only for the two-step door interaction.
    v1.emit_ray_helpers(a)
    emit_mul_u8(a); emit_div_u16_u8_sat(a); emit_div_u16_u8_sat9(a); emit_signed_math(a)
    emit_dda(a); emit_projection_and_casting(a); emit_renderer(a)
    emit_line_of_sight(a); emit_world_update(a); emit_entity_projection(a); emit_entity_renderer(a); emit_movement_v6(a); emit_reprojection(a)

    # Data section.
    a.align(16, text="data alignment")
    a.label("level_header"); a.bytes(ACTIVE_LEVEL.header_bytes(), "compiled active-level header")
    a.label("door_data"); a.bytes(ACTIVE_LEVEL.door_bytes(), "fixed-capacity authored door records")
    a.label("map_data"); a.bytes(make_map(), "compiled 16x16 world map")
    a.label("ui_tiles"); a.bytes(make_ui_tiles(), "HUD / utility tiles 240-255")
    a.label("weapon_tiles"); a.bytes(make_weapon_tiles(), "32x32 weapon tiles 240-255")
    a.label("static_view_tiles"); a.bytes(make_static_view_tiles(), "ceiling/floor plus phase-free seam atlas")
    a.label("active_atlas_tiles"); a.bytes(ACTIVE_ATLAS_TILES, "active profile exact tile atlas")
    a.label("entity_tiles"); a.bytes(make_entity_tiles(), "Sentinel, pickup and hit-effect OBJ tiles")
    a.label("oam_initial"); a.bytes(make_oam_shadow(), "weapon/UI-first atomic OAM shadow")
    a.label("oam_dma_stub"); a.bytes(bytes((0x3E, 0xC8, 0xE0, OAM_DMA, 0x3E, 0x50, 0x3D, 0x20, 0xFD, 0xC9)), "HRAM OAM-DMA wait stub")
    a.label("tilemap_data"); a.bytes(make_tilemap(), "base 32x32 tile-number map")
    a.label("attrmap_page0"); a.bytes(make_attrmap(0), "page 0 CGB attributes")
    a.label("attrmap_page1"); a.bytes(make_attrmap(1), "page 1 CGB attributes")

    wall_light, wall_dark = rgb15(24, 18, 10), rgb15(12, 7, 5)
    bg_palette_values = [
        rgb15(2, 3, 4), rgb15(8, 7, 6), wall_light, wall_dark,
        rgb15(1, 1, 1), rgb15(6, 5, 5), rgb15(27, 24, 17), rgb15(27, 3, 3),
        rgb15(3, 4, 5), rgb15(8, 8, 7), wall_light, wall_dark,
        rgb15(4, 5, 6), rgb15(9, 8, 7), wall_light, wall_dark,
        rgb15(5, 6, 7), rgb15(10, 9, 7), wall_light, wall_dark,
        rgb15(6, 7, 8), rgb15(11, 9, 7), wall_light, wall_dark,
        rgb15(7, 8, 9), rgb15(12, 10, 7), wall_light, wall_dark,
        rgb15(7, 8, 9), rgb15(12, 10, 7), wall_light, wall_dark,
    ]
    obj_palette_values = [
        rgb15(0, 0, 0), rgb15(8, 5, 3), rgb15(15, 16, 15), rgb15(28, 25, 18),
        rgb15(0, 0, 0), rgb15(24, 3, 2), rgb15(31, 19, 1), rgb15(30, 29, 22),
    ]
    a.align(256, text="legacy movement table alignment")
    for name in ("step_dx", "step_dy", "move_dx", "move_dy"):
        a.label(name); a.bytes(tables[name], name)
    a.align(RAY_DIRECTION_COUNT, text=f"{RAY_DIRECTION_COUNT}-direction ray table alignment")
    a.label("ray_vectors_packed"); a.bytes(tables["ray_packed"], "abs dx, abs dy, step x, step y")
    a.label("ray_offsets_q10"); a.bytes(tables["ray_offsets"], "80 signed 10-bit camera-plane offsets")
    a.label("ray_corrections"); a.bytes(tables["ray_corrections"], "80 cosine correction factors")
    a.label("physical_offsets_q10"); a.bytes(tables["physical_offsets"], "160 signed physical-pixel offsets")
    a.label("physical_corrections"); a.bytes(tables["physical_corrections"], "160 physical-pixel cosine corrections")
    a.label("top_depth_lut"); a.bytes(make_top_depth_lut(), "projected-top to conservative corrected Q5 depth")
    a.label("seam_tile_lookup"); a.bytes(make_seam_tile_lookup(), "dark-mask to static seam tile lookup")
    a.label("active_atlas_bucket_start"); a.bytes(ACTIVE_ATLAS_BUCKET_START, "active-profile signature-hash bucket starts")
    a.label("active_atlas_bucket_count"); a.bytes(ACTIVE_ATLAS_BUCKET_COUNT, "active-profile signature-hash bucket counts")
    a.label("active_atlas_entries"); a.bytes(ACTIVE_ATLAS_ENTRIES, "active-profile exact signatures and tile IDs")
    microstrips = make_microstrips()
    style_block = MICRO_STATE_COUNT * 8 * 16
    a.label("microstrip_style_bases")
    for style in range(2): a.dw_label(f"microstrips_style_{style}")
    for style in range(2):
        a.label(f"microstrips_style_{style}")
        a.bytes(microstrips[style * style_block:(style + 1) * style_block], f"style {style} edge microstrips")
    pair_microstrips = make_pair_microstrips()
    pair_style_block = MICRO_STATE_COUNT * 4 * 16
    a.label("pair_microstrip_style_bases")
    for style in range(2): a.dw_label(f"pair_microstrips_style_{style}")
    for style in range(2):
        a.label(f"pair_microstrips_style_{style}")
        a.bytes(pair_microstrips[style * pair_style_block:(style + 1) * pair_style_block], f"style {style} pair microstrips")
    # Palettes are cold startup data. Keeping them after the aligned hot tables
    # avoids wasting a complete 1 KiB alignment page as the resident art/UI
    # vocabulary grows.
    a.label("bg_palettes"); a.bytes(words_le(bg_palette_values), "eight CGB BG palettes")
    a.label("obj_palettes"); a.bytes(words_le(obj_palette_values), "two CGB OBJ palettes")

    code = a.resolve()
    metadata = {
        "engine_origin": a.origin,
        "engine_end": a.origin + len(code),
        "engine_size": len(code),
        "renderer": "segment-certified Q5 DDA + hybrid wall/entity compositor",
        "framebuffer_bytes": 0,
        "dynamic_tile_capacity": DYNAMIC_TILE_CAPACITY,
        "dynamic_tile_buffer_bytes": DYNAMIC_TILE_CAPACITY * 16,
        "view_map_buffer_bytes": 384,
        "maximum_commit_bytes": DYNAMIC_TILE_CAPACITY * 16 + 384,
        "maximum_commit_blocks": DYNAMIC_TILE_CAPACITY + 24,
        "rays": RAYS,
        "physical_columns": PHYSICAL_COLUMNS,
        "ray_width_pixels": RAY_WIDTH,
        "adaptive_anchor_casts": 41,
        "adaptive_validation": "same axis/material/plane, adjacent face cells, and <=2-pixel anchor slope",
        "ray_direction_table_entries": RAY_DIRECTION_COUNT,
        "packed_direction_record_bytes": 4,
        "shared_frame_boundary_fractions": True,
        "ray_vector_scale": RAY_VECTOR_SCALE,
        "projection_fractional_bits": 5,
        "selective_edge_recasts": True,
        "ray_depth_buffer_bytes": RAYS,
        "ray_segment_buffer_bytes": RAYS,
        "pixel_segment_buffer_bytes": PHYSICAL_COLUMNS,
        "segment_aware_reconstruction": True,
        "material_geometry_decoupled": True,
        "viewport": list(VIEWPORT),
        "map": [16, 16],
        "wall_styles": STYLE_COUNT,
        "render_styles": RENDER_STYLE_COUNT,
        "wall_material_names": list(WALL_MATERIAL_NAMES),
        "wall_pattern_resolution_pairs": [1, 1],
        "full_width_contrast_bands": 0,
        "world_anchored_face_events": True,
        "world_height_surface_rails": SURFACE_DETAIL_ENABLED,
        "surface_detail_profile": "legacy rail" if SURFACE_DETAIL_ENABLED else "spatial clarity",
        "live_hud_fields": ["health", "exit_objective"],
        "vblank_input_sampling": True,
        "input_edge_latching": True,
        "render_pose_mutated_by_interrupts": False,
        "palette_depth_ladder_enabled": False,
        "palette_depth_ladder_rejection": "ROM playtest exposed screen-space horizontal banding",
        "static_view_tiles": STATIC_VIEW_TILES,
        "vram_profile": "entity-heavy" if ACTIVE_LEVEL.vram_profile == VRAM_PROFILE_ENTITY else "renderer-heavy",
        "renderer_atlas_patterns": len(RENDERER_ATLAS_TILES) // 16,
        "entity_atlas_patterns": len(ENTITY_ATLAS_TILES) // 16,
        "entity_tile_ids": [ENTITY_TILE_BASE, EXIT_BEACON_TILE + EXIT_BEACON_FRAMES - 1],
        "oam_shadow_bytes": OAM_BYTES,
        "oam_reserved_ui_entries": ENTITY_OAM_FIRST,
        "oam_entity_capacity": ENTITY_OAM_COUNT,
        "sentinel_states": ["dormant", "patrol", "chase", "attack", "hurt", "dead"],
        "level_format": ACTIVE_LEVEL.format,
        "active_level": ACTIVE_LEVEL.name,
        "active_level_doors": len(ACTIVE_LEVEL.doors),
        "maximum_level_doors": MAX_DOORS,
        "walkable_level_cells": ACTIVE_LEVEL.readability.walkable_cells,
        "unreachable_level_cells": ACTIVE_LEVEL.readability.unreachable_cells,
        "critical_path_steps": ACTIVE_LEVEL.readability.critical_path_steps,
        "critical_path_turns": ACTIVE_LEVEL.readability.critical_path_turns,
        "maximum_level_sightline": ACTIVE_LEVEL.readability.maximum_sightline,
        "maximum_open_rectangle": list(ACTIVE_LEVEL.readability.maximum_open_rectangle),
        "minimum_door_separation": ACTIVE_LEVEL.readability.minimum_door_separation,
        "material_surface_seams": ACTIVE_LEVEL.readability.material_seams,
        "material_singleton_runs": ACTIVE_LEVEL.readability.material_singleton_runs,
        "physical_surface_segments": ACTIVE_LEVEL.readability.physical_segments,
        "safe_spawn_radius_cells": ACTIVE_LEVEL.safe_radius_cells,
        "exit_beacon": True,
        "player_collision_radius_q8": PLAYER_RADIUS_Q8,
        "animated_door": True,
        "micro_reprojection_compiled": ENABLE_MICRO_REPROJECTION,
        "micro_reprojection_limit_pixels": REPROJECT_LIMIT,
        "microstrip_states": MICRO_STATE_COUNT,
        "microstrip_rom_bytes": len(microstrips) + len(pair_microstrips),
        "hram_hot_state_bytes": HRAM_BYTES_USED,
        "hram_hot_state_range": [min(HRAM_LAYOUT.values()), max(HRAM_LAYOUT.values())],
        "projection_lut_bytes": PROJECTION_LUT_BYTES,
        "projection_lut_banks": PROJECTION_LUT_BYTES // 0x4000,
        "projection_lut_base_bank": PROJECTION_LUT_BASE_BANK,
        "projection_lut_exact": True,
        "product_lut_bytes": PRODUCT_LUT_BYTES,
        "product_lut_banks": PRODUCT_LUT_BYTES // 0x4000,
        "product_lut_base_bank": PRODUCT_LUT_BASE_BANK,
        "product_lut_exact": True,
        "rom_banks": ROM_BANKS,
        "cartridge_type": "MBC5",
    }
    return code, a, metadata


def make_rom() -> tuple[bytes, Assembler, dict[str, object]]:
    engine, assembler, metadata = build_engine()
    if 0x0150 + len(engine) > 0x8000:
        raise RuntimeError(f"resident engine does not fit banks 0/1: end={0x0150 + len(engine):04X}")
    rom = bytearray([0xFF] * ROM_BYTES)
    rom[0x0100:0x0104] = bytes((0x00, 0xC3, 0x50, 0x01))
    rom[0x0104:0x0134] = NINTENDO_LOGO
    rom[0x0134:0x0143] = b"LUPINE3D".ljust(15, b"\0")
    rom[0x0143] = 0xC0; rom[0x0144:0x0146] = b"00"; rom[0x0146] = 0
    rom[0x0147] = 0x19; rom[0x0148] = 0x07; rom[0x0149] = 0; rom[0x014A] = 1; rom[0x014B] = 0x33; rom[0x014C] = 6
    rom[0x0150:0x0150 + len(engine)] = engine
    vblank_isr = assembler.labels["vblank_isr"]
    rom[0x0040:0x0043] = bytes((0xC3, vblank_isr & 0xFF, vblank_isr >> 8))
    if ENABLE_MICRO_REPROJECTION:
        stat_isr = assembler.labels["stat_isr"]
        rom[0x0048:0x004B] = bytes((0xC3, stat_isr & 0xFF, stat_isr >> 8))
    projection_lut = make_projection_top_lut()
    lut_start = PROJECTION_LUT_BASE_BANK * 0x4000
    rom[lut_start:lut_start + len(projection_lut)] = projection_lut
    product_lut = make_product_lut()
    product_start = PRODUCT_LUT_BASE_BANK * 0x4000
    rom[product_start:product_start + len(product_lut)] = product_lut
    banked_atlas_payload = b"".join((
        BANKED_ATLAS_TILES, BANKED_ATLAS_BUCKET_START,
        BANKED_ATLAS_BUCKET_COUNT, BANKED_ATLAS_ENTRIES,
    ))
    banked_atlas_start = BANKED_ATLAS_ROM_BANK * 0x4000
    rom[banked_atlas_start:banked_atlas_start + len(banked_atlas_payload)] = banked_atlas_payload
    segment_start = SEGMENT_TABLE_ROM_BANK * 0x4000
    segment_table = make_segment_table()
    rom[segment_start:segment_start + len(segment_table)] = segment_table
    chk = 0
    for value in rom[0x0134:0x014D]: chk = (chk - value - 1) & 0xFF
    rom[0x014D] = chk
    rom[0x014E] = rom[0x014F] = 0
    total = sum(rom) & 0xFFFF
    rom[0x014E] = (total >> 8) & 0xFF; rom[0x014F] = total & 0xFF
    metadata.update({
        "header_checksum": chk, "global_checksum": total, "title": "LUPINE3D",
        "cgb_flag": "0xC0 (CGB-only)", "rom_size_bytes": len(rom),
        "sha256": hashlib.sha256(rom).hexdigest(),
        "symbols": {k: f"0x{v:04X}" for k, v in sorted(assembler.labels.items(), key=lambda item: item[1])},
    })
    return bytes(rom), assembler, metadata


def main() -> None:
    rom, assembler, metadata = make_rom()
    rom_path = BUILD / "lupine3d.gb"; rom_path.write_bytes(rom)
    assembler.write_listing(BUILD / "lupine3d.lst")
    (BUILD / "lupine3d.sym").write_text("\n".join(f"{addr:04X} {name}" for name, addr in sorted(assembler.labels.items(), key=lambda item: item[1])) + "\n", encoding="utf-8")
    (BUILD / "build_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Built {rom_path} ({len(rom)} bytes)")
    print(f"Engine: {metadata['engine_size']} bytes, end={metadata['engine_end']:#06x}")
    print(f"Header checksum: {metadata['header_checksum']:#04x}; global: {metadata['global_checksum']:#06x}")


if __name__ == "__main__":
    main()
