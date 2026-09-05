#!/usr/bin/env python3
"""Compatibility facade and ROM linker for Lupine 3D.

Implementation details live in ``lupine3d_v4``.  Tests and research tools may
continue importing this module as ``build_rom`` without API churn.
"""
from __future__ import annotations

import hashlib
import json
import argparse

from lupine3d_v4.layout import *  # noqa: F401,F403
from lupine3d_v4.resources import *  # noqa: F401,F403
from lupine3d_v4.reference import *  # noqa: F401,F403
from lupine3d_v4.emitter import *  # noqa: F401,F403
from lupine3d_v4.living_world import *  # noqa: F401,F403
# living_world re-exports the compatibility layout namespace. Reassert the
# current art generators after that import so the frozen v0.1 helpers cannot
# shadow the active industrial-gothic UI and weapon assets.
from lupine3d_v4.resources import make_ui_tiles, make_weapon_tiles, make_obj_ui_tiles  # noqa: E402
from lupine3d_v4.precision import make_q14_directions, emit_precision
from lupine3d_v4.actor_precision import emit_actor_precision
from lupine3d_v4.admission import emit_admission
from lupine3d_v4.projection_storage import pack_projection, emit_projection_storage
from lupine3d_v4.near_field import near_corrections, emit_near_field
from lupine3d_v4.foreground import emit_foreground
from lupine3d_v4.door_geometry import emit_door_geometry
from lupine3d_v4.simulation import emit_simulation, emit_copy_bulk
from lupine3d_v4.masked_entities import emit_masked_entities, emit_entity_renderer_v7
from lupine3d_v4.actors import actor_records, emit_actors
from lupine3d_v4.surfaces import emit_surfaces, surface_attributes
from lupine3d_v4.artwork import hud_assets
from lupine3d_v4.world_decor import emit_world_decor, fixture_records
from lupine3d_v4.wall_cache import emit_wall_cache
from lupine3d_v4.ray_setup import make_ray_setup_table, emit_ray_setup
from lupine3d_v4 import layout as active_layout
from lupine3d_v4.allocation import memory_ledger
from lupine3d_v4.configuration import identity
from lupine3d_v4.tile_cache import emit_tile_cache
from lupine3d_v4.packets import emit_packets
from lupine3d_v4.physical_depth import emit_physical_depth

def make_boot_assets() -> list[tuple[str, bytes]]:
    """Cold assets share one ROM bank; no runtime arithmetic bank owns them."""
    return [
        ("ui_tiles", make_ui_tiles()), ("hud_tiles", hud_assets()[0]), ("weapon_tiles", make_weapon_tiles()), ("obj_ui_tiles", make_obj_ui_tiles()),
        ("static_view_tiles", make_static_view_tiles()),
        ("active_atlas_tiles", ACTIVE_ATLAS_TILES),
        ("entity_tiles", make_entity_tiles()), ("oam_initial", make_oam_shadow()),
        # Pan Docs HRAM loop: 40 * four M-cycles covers the 160-M-cycle DMA.
        ("oam_dma_stub", bytes((0x3E, 0xC8, 0xE0, OAM_DMA, 0x3E, 40, 0x3D, 0x20, 0xFD, 0xC9))),
        ("tilemap_data", make_tilemap()), ("attrmap_page0", make_attrmap(0)),
        ("attrmap_page1", make_attrmap(1)),
        ("map_data", make_map()),
    ]

def build_engine() -> tuple[bytes, Assembler, dict[str, object]]:
    tables = make_tables()
    a = Assembler(origin=0x0150, optimize_high_page=True)
    a.label("start")
    a.di(); a.ld_rr_nn("sp", STACK_TOP); a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
    a.xor_r("a"); a.ld_abs_a(0xFFFF); a.ld_abs_a(0xFF0F)
    a.ld_r_n("a", 1); a.ldh_n_a(KEY1); a.stop()
    a.label("startup_wait_vblank")
    a.ldh_a_n(LY); a.cp_n(144); a.jr("startup_wait_vblank", "c")
    a.xor_r("a"); a.ldh_n_a(LCDC); a.ldh_n_a(SCX); a.ldh_n_a(SCY)
    for address in (WALL_CACHE_VALID, FRAME_REUSED, PRESENT_SERIAL, WALL_CACHE_DISABLE, WALL_EPOCH, WALL_EPOCH + 1):
        a.ld_abs_a(address)
    if PHYSICAL_DEPTH: a.ld_abs_a(COVERAGE_MODE)
    if FOREGROUND_PUBLICATION:
        for address in range(FG_HEAD,FG_CHANGED+1): a.ld_abs_a(address)
    a.ld_r_n("a", 1); a.ld_abs_a(OBJ_PAGE)
    if SABLE_ART or COMPACT_DISPLAY:
        a.xor_r("a")
        for address in (SIM_TICK,SIM_TICK+1,FRAME_TICK,FRAME_TICK+1):a.ld_abs_a(address)
    a.call("load_level")
    a.xor_r("a"); a.ld_abs_a(BUTTONS); a.ld_abs_a(PREV_BUTTONS); a.ld_abs_a(FLASH); a.ld_abs_a(CURRENT_PAGE); a.ld_abs_a(DYN_HIGH_WATER)
    a.ld_abs_a(INPUT_LAST_RAW); a.ld_abs_a(INPUT_EDGE_LATCH); a.ld_abs_a(INPUT_SAMPLE_COUNT)
    a.ld_abs_a(SIM_READY)
    a.ld_r_n("a", 255); a.ld_abs_a(Q14_RECORD)
    a.call("init_palettes"); a.call("init_vram"); a.call("prepare_hud_tiles"); a.call("update_hud_tiles"); a.call("init_oam"); a.call("init_audio")
    if FOREGROUND_PUBLICATION:
        for i in range(2): a.ld_a_abs(WALL_EPOCH+i); a.ld_abs_a(FG_FRAME_GENERATION+i)
    a.call("cast_all")
    if PHYSICAL_DEPTH: a.call("refine_full_snapshot")
    a.call("render_view"); a.call("render_entities"); a.call("populate_reprojection_guards"); a.call("upload_initial_both_pages")
    if FOREGROUND_PUBLICATION: a.call("finish_foreground_commit")
    a.ld_r_n("a", BG_LCDC); a.ldh_n_a(LCDC)
    a.xor_r("a"); a.ld_abs_a(0xFF0F)
    if ENABLE_MICRO_REPROJECTION or HUD_UNSIGNED:
        a.ld_r_n("a", VIEW_HEIGHT); a.ldh_n_a(LYC); a.ld_r_n("a", 0x40); a.ldh_n_a(STAT)
        a.ld_r_n("a", 3); a.ld_abs_a(0xFFFF)
    else:
        a.ld_r_n("a", 1); a.ld_abs_a(0xFFFF)
    a.ei(); a.nop()
    a.call("wait_vblank"); a.call("init_simulation")
    a.label("main_loop")
    if FIXED_SIMULATION:
        a.call("begin_frame_snapshot")
    else:
        a.call("update_input"); a.call("update_world")
    a.call("check_wall_reuse"); a.or_r("a"); a.jr("reuse_wall_view", "nz")
    a.call("cast_all")
    if PHYSICAL_DEPTH: a.call("refine_full_snapshot")
    a.label("compose_full_snapshot")
    a.call("render_view"); a.call("render_entities"); a.call("populate_reprojection_guards"); a.call("upload_hidden_page"); a.jp("main_loop")
    a.label("reuse_wall_view")
    if PHYSICAL_DEPTH:
        a.call("refine_reused_snapshot"); a.or_r("a"); a.jp("compose_full_snapshot","nz")
    a.call("render_entities"); a.call("upload_entities_hud"); a.jp("main_loop")

    # Runtime routines.
    emit_copy_bulk(a); v1.emit_wait_vblank(a); emit_palette_init(a); emit_hud_system(a)
    emit_level_loader(a); emit_vram_init(a); emit_oam_system(a); emit_door_system(a); v1.emit_audio(a); emit_dma(a); emit_input_system(a)
    # Legacy quarter-step helpers are retained only for the two-step door interaction.
    v1.emit_ray_helpers(a)
    emit_mul_u8(a); emit_div_u16_u8_sat(a); emit_div_u16_u8_sat9(a); emit_signed_math(a)
    if PREPARED_RAYS: emit_ray_setup(a)
    emit_dda(a); emit_projection_and_casting(a); emit_renderer(a)
    emit_precision(a)
    emit_packets(a)
    emit_physical_depth(a)
    emit_actor_precision(a)
    from lupine3d_v4.animation import emit_animation
    emit_animation(a)
    emit_admission(a)
    emit_projection_storage(a)
    emit_near_field(a)
    emit_foreground(a)
    emit_door_geometry(a)
    emit_simulation(a)
    emit_wall_cache(a)
    emit_tile_cache(a)
    emit_actors(a)
    emit_surfaces(a)
    emit_world_decor(a)
    emit_line_of_sight(a); emit_world_update(a); emit_entity_projection(a); emit_entity_renderer_v7(a); emit_masked_entities(a); emit_movement_v6(a); emit_reprojection(a)

    # Data section.
    a.align(16, text="data alignment")
    a.label("level_header"); a.bytes(ACTIVE_LEVEL.header_bytes(), "compiled active-level header")
    a.label("door_data"); a.bytes(ACTIVE_LEVEL.door_bytes(), "fixed-capacity authored door records")
    a.label("actor_records"); a.bytes(actor_records(), "four bounded Sentinel slots")
    a.label("hud_status_records"); a.bytes(bytes(i for label in ("LOCK", "OPEN", "DEAD", "DONE") for i in ((hud_assets()[3]["caption_"+label] if COMPACT_DISPLAY else []) + hud_assets()[3][label])), "LOCK OPEN DEAD DONE")
    cold_address = 0x4000
    for name, payload in make_boot_assets():
        a.labels[name] = cold_address
        cold_address += len(payload)
    assert cold_address <= 0x8000, "cold boot assets exceed one MBC5 bank"

    wall_light, wall_dark = rgb15(14, 17, 18), rgb15(6, 9, 11)
    bg_palette_values = [
        rgb15(1, 2, 3), rgb15(5, 6, 7), wall_light, wall_dark,
        rgb15(2, 3, 4), rgb15(5, 7, 8), rgb15(26, 27, 23), rgb15(12, 15, 16),
        rgb15(3, 4, 5), rgb15(8, 8, 7), wall_light, wall_dark,
        rgb15(4, 5, 6), rgb15(9, 8, 7), wall_light, wall_dark,
        rgb15(5, 6, 7), rgb15(10, 9, 7), wall_light, wall_dark,
        rgb15(6, 7, 8), rgb15(11, 9, 7), wall_light, wall_dark,
        rgb15(7, 8, 9), rgb15(12, 10, 7), wall_light, wall_dark,
        rgb15(7, 8, 9), rgb15(12, 10, 7), wall_light, wall_dark,
    ]
    obj_palette_values = [
        0, rgb15(2, 3, 4), rgb15(12, 15, 17), rgb15(24, 26, 25),
        0, rgb15(3, 2, 3), rgb15(20, 5, 4), rgb15(28, 24, 17),
        0, rgb15(2, 5, 4), rgb15(5, 18, 11), rgb15(27, 29, 23),
        0, rgb15(2, 3, 4), rgb15(8, 12, 14), rgb15(30, 22, 8),
        0, rgb15(2, 5, 6), rgb15(5, 15, 18), rgb15(16, 29, 27),
        0, rgb15(3, 3, 3), rgb15(13, 8, 5), rgb15(22, 16, 10),
        0, rgb15(2, 3, 4), rgb15(20, 24, 23), rgb15(13, 28, 26),
        0, rgb15(6, 1, 1), rgb15(31, 7, 3), rgb15(31, 26, 17),
    ]
    if SABLE_ART:
        from lupine3d_v4.sprite_assets import manifest as sprite_manifest
        for index,name in ((0,'shotgun'),(1,'sentinel_near')):
            colours=sprite_manifest()['assets'][name]['palette']
            obj_palette_values[index*4:index*4+4]=[rgb15(*(round(c*31/255) for c in rgb)) for rgb in colours]
    if COMPACT_DISPLAY:
        bg_palette_values[4:8]=[rgb15(2,3,4),rgb15(5,7,8),rgb15(29,28,24),rgb15(10,16,16)]
        if SLIM_DISPLAY:
            from lupine3d_v4.steel_hud import PALETTE
            bg_palette_values[4:8]=[rgb15(*(round(c*31/255) for c in rgb)) for rgb in PALETTE]
    # Lower-half Y-flip reuses upper patterns; outside-wall colour zero
    # becomes the floor without recolouring a single wall pixel. The same
    # pair also preserves unfurled colour-index-one floor pixels.
    bg_palette_values[8:12] = [bg_palette_values[1], *bg_palette_values[1:4]]
    # Cyan/white is reserved for operating doors. Cool green marks machinery;
    # neutral steel carries structure. All profiles share ceiling/floor RGB.
    for upper, lower, light, dark in ((3, 4, rgb15(3, 13, 16), rgb15(15, 27, 25)),
                                       (5, 6, rgb15(10, 14, 12), rgb15(4, 8, 7))):
        bg_palette_values[upper * 4:upper * 4 + 4] = [bg_palette_values[0], bg_palette_values[1], light, dark]
        bg_palette_values[lower * 4:lower * 4 + 4] = [bg_palette_values[1], bg_palette_values[1], light, dark]
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
    microstrips = make_microstrips(STORED_STRIP_STATES)
    style_block = STORED_STRIP_COUNT * 8 * 16
    a.label("microstrip_style_bases")
    for style in range(2): a.dw_label(f"microstrips_style_{style}")
    for style in range(2):
        if FOLDED_COMPOSITOR:
            a.label(f"microstrips_style_{style}")
            a.bytes(microstrips[style * style_block:(style + 1) * style_block], f"style {style} edge microstrips")
        else:
            a.labels[f"microstrips_style_{style}"] = 0x4000 + style * style_block
    pair_microstrips = make_pair_microstrips(STORED_STRIP_STATES)
    pair_style_block = STORED_STRIP_COUNT * 4 * 16
    a.label("pair_microstrip_style_bases")
    for style in range(2): a.dw_label(f"pair_microstrips_style_{style}")
    for style in range(2):
        if FOLDED_COMPOSITOR:
            a.label(f"pair_microstrips_style_{style}")
            a.bytes(pair_microstrips[style * pair_style_block:(style + 1) * pair_style_block], f"style {style} pair microstrips")
        else:
            a.labels[f"pair_microstrips_style_{style}"] = 0x4000 + len(microstrips) + style * pair_style_block
    # Fixtures have no alignment requirement; the startup map is cold/banked.
    a.label("wall_fixture_records"); a.bytes(fixture_records(), "wall-mounted landmarks")
    if NEAR_FIELD:
        a.label("near_correction_q14"); a.bytes(words_le(near_corrections()), "241 Q14 camera-plane cosine corrections")
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
        "memory_budget": {
            "fixed_code_end": a.labels["level_header"],
            "cold_assets_bank": BOOT_ASSETS_ROM_BANK,
            "cold_assets_bytes": cold_address - 0x4000,
            "resident_free_bytes": 0x8000 - (a.origin + len(code)),
            "stack_top": STACK_TOP,
            "stack_reserved_bytes": 0x200,
            "hram_state_bytes": HRAM_BYTES_USED,
            "hram_dma_bytes": OAM_DMA_STUB_BYTES,
            "vram_bg_pattern_range": [0x8800, 0x9800],
            "vram_obj_only_range": [0x8000, 0x8800],
            "bank1_obj_patterns_used": ENTITY_OAM_COUNT * 2 + (86 if SABLE_ART else 20),
            "bank0_hud_patterns_used": len(hud_assets()[0]) // 16,
        },
        "renderer": "certified Q14 crossing order, Q5 projection, folded signed-BG compositor and masked 8x16 entities",
        "q14_continuation": "resume from the last certified cell; restart axial and origin-door casts",
        "door_division": "register-resident 16-bit quotient, four bits per group, unsigned overflow rejection",
        "streaming_columns": True,
        "streaming_surface_events": True,
        "prepared_ray_setup": PREPARED_RAYS,
        "prepared_ray_table_bank": RAY_SETUP_ROM_BANK,
        "prepared_ray_table_bytes": RAY_SETUP_ROM_BYTES if PREPARED_RAYS else 0,
        "prepared_ray_format": {"version": 3 if PROJECTION_STORAGE != "direct" else 2 if ANCHOR_PACKETS else 1,
                                "scalar_records": [0,241], "packet_records": [241,251] if ANCHOR_PACKETS else [],
                                "projection_fields": "logical slice u16" if PROJECTION_STORAGE != "direct" else "physical bank/high byte",
                                "record_bytes": 16, "raw_sentinel": 255},
        "anchor_packet_workspace_bytes": 96 if ANCHOR_PACKETS else 0,
        "anchor_packet_max_pending_siblings": 2 if ANCHOR_PACKETS else 0,
        "prepared_ray_wram_bytes": (8 if CAMERA_SETUP else 4) if PREPARED_RAYS else 0,
        "dynamic_cache_format": {
            "version": 1, "enabled": DYNAMIC_TILE_CACHE, "wram_bank": 3,
            "entry_count": 128, "entry_bytes": 32, "signature_bytes": 10,
            "index_hash": "atlas_xor_first_top" if CACHE_KEY_MIX else "atlas_signature",
            "valid_offset": 0, "profile_offset": 1, "generation_offset": 2,
            "signature_offset": 4, "pattern_offset": 14,
            "staging_range": [DYNAMIC_CACHE_STAGE, DYNAMIC_CACHE_POINTER+2],
        },
        "publication": "atomic BG/HUD/OAM; compact high-pressure packets use three VBlanks" if COMPACT_DISPLAY else "atomic BG/HUD/OAM; large hidden-pattern packets staged across two VBlanks",
        "framebuffer_bytes": 0,
        "signed_bg_tile_addressing": True,
        "folded_compositor": FOLDED_COMPOSITOR,
        "composited_tile_rows": FOLDED_ROWS if FOLDED_COMPOSITOR else VIEW_ROWS,
        "obj_only_patterns_per_bank": 128,
        "art_direction": "Sable Outpost",
        "display_configuration": {"name": RENDER_CONFIG["display"], "viewport": list(VIEWPORT),
                                  "horizon": HORIZON, "hud_height": HUD_HEIGHT, "map_bytes": VIEW_MAP_BYTES,
                                  "hud_theme": "steel-objective-spaced-v1" if SLIM_DISPLAY else "sable-strip" if COMPACT_DISPLAY else "legacy",
                                  "extra_cpu_bytes_per_full_packet": (VIEW_MAP_BYTES-384)*2},
        "native_art": __import__('lupine3d_v4.sprite_assets', fromlist=['evidence']).evidence() if SABLE_ART or COMPACT_DISPLAY else None,
        "art_animation": ART_ANIMATION,
        "foreground_obj_allocation": {"first":WEAPON_TILE_BASE,"patterns":86 if SABLE_ART else 20,
                                      "reticle":RETICLE_TILE,"flash":MUZZLE_TILE},
        "entity_source_patterns":len(make_entity_tiles())//16,
        "hud_patterns": len(hud_assets()[0]) // 16,
        "hud_unsigned_bank0_range": [0x8200, 0x8800],
        "hud_stat_split_line": VIEW_HEIGHT,
        "hud_packet_bytes": HUD_PACKET_BYTES,
        "hud_status_pattern_format": {
            "version": 2 if SLIM_DISPLAY else 1,
            "vertical_pair_ids": SLIM_DISPLAY,
            "lower_tile_id_delta": 1 if SLIM_DISPLAY else 0,
            "extra_map_writes_per_commit": 6 if SLIM_DISPLAY else 0,
        },
        "authored_wall_fixtures": len(ACTIVE_LEVEL.fixtures),
        "wall_fixture_oam_budget": 4,
        "wall_fixture_occlusion": "physical segment and along-face cell stencil",
        "single_vblank_pattern_budget": 24,
        "oam_dma_wait_mcycles": 160,
        "camera_focal_pixels": CAMERA_FOCAL_PIXELS,
        "cast_depth_source": "queried physical columns in Q5 with per-column validity" if PHYSICAL_DEPTH else "paired projection LUT; interpolated samples retain conservative height bounds",
        "physical_depth_format": {"version": 1, "enabled": PHYSICAL_DEPTH,
                                  "depth_address": PIXEL_DEPTH, "depth_bytes": 160,
                                  "validity_address": PIXEL_DEPTH_VALID, "validity_bytes": 20,
                                  "coverage_address": PHYSICAL_COVERAGE, "coverage_bytes": 20,
                                  "meaning": "actual query under current exact wall key and projection configuration; Q5"},
        "dynamic_tile_capacity": DYNAMIC_TILE_CAPACITY,
        "dynamic_tile_buffer_bytes": DYNAMIC_TILE_CAPACITY * 16,
        "view_map_buffer_bytes": VIEW_MAP_BYTES,
        "maximum_commit_bytes": DYNAMIC_TILE_CAPACITY * 16 + 768 + ENTITY_OAM_COUNT * 32,
        "maximum_commit_blocks": DYNAMIC_TILE_CAPACITY + 48 + ENTITY_OAM_COUNT * 2,
        "maximum_first_stage_blocks": DYNAMIC_TILE_CAPACITY,
        "maximum_final_stage_blocks": 72 if FOREGROUND_PUBLICATION else 48 + ENTITY_OAM_COUNT * 2,
        "maximum_publication_vblanks": 3 if FOREGROUND_PUBLICATION or ENABLE_MICRO_REPROJECTION else 2,
        "fixed_tick_simulation": FIXED_SIMULATION,
        "exact_wall_reuse": WALL_REUSE_ENABLED,
        "wall_cache_key_bytes": 290,
        "independent_obj_page": True,
        "presentation_serial_address": PRESENT_SERIAL,
        "simulation_tick_hz": 4194304 / 70224,
        "simulation_clock_bits": 16,
        "timestamped_input_capacity": INPUT_QUEUE_CAPACITY - 1,
        "live_world_wram_bank": 2,
        "render_snapshot_wram_bank": 1,
        "sliding_door_geometry": "Q8 centre-plane finite segment, shared by rays/LOS/hitscan/radius collision",
        "actor_slot_capacity": MAX_ACTORS,
        "active_actor_count": len(ACTIVE_LEVEL.entities),
        "entity_size_lods": [[16, 32], [16, 16], [8, 16]],
        "masked_obj_patterns": ENTITY_OAM_COUNT * 2,
        "hardware_obj_size": [8, 16],
        "world_obj_limit_per_scanline": 10 if SCANLINE_ADMISSION else 4,
        "world_obj_scanline_accounting": "actual foreground Y occupancy plus world objects" if SCANLINE_ADMISSION else "six foreground slots reserved on every line",
        "actor_projection_format": {"version":2 if ACTOR_PRECISION else 1,"position_fractional_bits":8 if ACTOR_PRECISION else 4,
                                    "camera_fractional_bits":14 if ACTOR_PRECISION else 6,"product_bits":32 if ACTOR_PRECISION else 16,
                                    "transform_rounding":"nearest, ties toward +infinity" if ACTOR_PRECISION else "arithmetic truncation"},
        "foreground_format": {"version":1,"enabled":FOREGROUND_PUBLICATION,"wram_bank":4,
                              "queue_capacity":15,"record_bytes":10,"fields":["sequence_u16","sample_tick_u16","accept_tick_u16","scene_generation_u16","type_u8","reserved_u8"],
                              "vblank_event_limit":2,"world_prepare_event_limit":4,"dma_buffer":FG_COMPOSITE_OAM,
                              "published_oam":FG_PUBLISHED_OAM,"full_geometry_counter_unchanged":True},
        "near_field_format": {"version":1,"enabled":NEAR_FIELD,"limit_q8":512,"far_field":"legacy Q5",
                             "perpendicular_fractional_bits":8,"plane_components_fractional_bits":14,"output_depth_fractional_bits":5},
        "surface_profile_records": len(ACTIVE_LEVEL.surface_table),
        "rays": RAYS,
        "physical_columns": PHYSICAL_COLUMNS,
        "ray_width_pixels": RAY_WIDTH,
        "adaptive_anchor_casts": 41,
        "adaptive_validation": "same plane/material/segment/profile, adjacent face cells, and <=2-pixel anchor slope",
        "ray_direction_table_entries": RAY_DIRECTION_COUNT,
        "packed_direction_record_bytes": 4,
        "shared_frame_boundary_fractions": True,
        "ray_vector_scale": RAY_VECTOR_SCALE,
        "projection_fractional_bits": 5,
        "selective_edge_recasts": True,
        "certified_q14_crossing_order": Q14_ORDER_ENABLED,
        "q14_direction_rom_bytes": Q14_ROM_BYTES,
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
        "live_hud_fields": ["health", "remaining_hostiles", "exit_status"],
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
        "microstrip_format": {
            "version": 3 if SLIM_DISPLAY else 2, "logical_states": MICRO_STATE_COUNT,
            "stored_states": list(STORED_STRIP_STATES),
            "stored_state_count": STORED_STRIP_COUNT,
            "table_bytes": len(microstrips) + len(pair_microstrips),
            "table_bytes_saved": 7296 - len(microstrips) - len(pair_microstrips),
            "placement": "resident" if FOLDED_COMPOSITOR else "banked diagnostic",
            "bank": None if FOLDED_COMPOSITOR else UNFOLDED_STRIP_ROM_BANK,
            "scratch_bytes": 0 if FOLDED_COMPOSITOR else 16,
            "net_linked_savings_from_review": 29645 - a.origin - len(code),
        },
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
    configuration = dict(**RENDER_CONFIG, folded=FOLDED_COMPOSITOR,
                         q14=Q14_ORDER_ENABLED, prepared_rays=PREPARED_RAYS,
                         wall_reuse=WALL_REUSE_ENABLED, fixed_simulation=FIXED_SIMULATION,
                         reprojection=ENABLE_MICRO_REPROJECTION,
                         level=ACTIVE_LEVEL.name,
                         level_map_sha256=hashlib.sha256(make_map()).hexdigest(),
                         active_atlas_sha256=hashlib.sha256(ACTIVE_ATLAS_TILES + ACTIVE_ATLAS_ENTRIES).hexdigest())
    metadata["configuration"] = configuration
    metadata["configuration_id"] = identity(configuration)
    metadata["allocation_ledger"] = memory_ledger(active_layout, a.labels["level_header"],
                                                a.origin + len(code), cold_address - 0x4000)
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
    if not FOLDED_COMPOSITOR:
        strips = make_microstrips() + make_pair_microstrips()
        start = UNFOLDED_STRIP_ROM_BANK * 0x4000
        rom[start:start + len(strips)] = strips
    vblank_isr = assembler.labels["vblank_isr"]
    rom[0x0040:0x0043] = bytes((0xC3, vblank_isr & 0xFF, vblank_isr >> 8))
    if ENABLE_MICRO_REPROJECTION or HUD_UNSIGNED:
        stat_isr = assembler.labels["stat_isr"]
        rom[0x0048:0x004B] = bytes((0xC3, stat_isr & 0xFF, stat_isr >> 8))
    projection_lut, projection_format = pack_projection(PROJECTION_STORAGE)
    metadata["projection_storage_format"] = projection_format
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
    rom[segment_start + 1024:segment_start + 2048] = ACTIVE_LEVEL.surface_table
    boot_payload = b"".join(payload for _, payload in make_boot_assets())
    boot_start = BOOT_ASSETS_ROM_BANK * 0x4000
    rom[boot_start:boot_start + len(boot_payload)] = boot_payload
    q14_start = Q14_ROM_BANK * 0x4000
    rom[q14_start:q14_start + Q14_ROM_BYTES] = make_q14_directions()
    if PREPARED_RAYS:
        setup_start = RAY_SETUP_ROM_BANK * 0x4000
        assert setup_start >= q14_start + Q14_ROM_BYTES
        assert setup_start + RAY_SETUP_ROM_BYTES <= ROM_BYTES
        rom[setup_start:setup_start + RAY_SETUP_ROM_BYTES] = make_ray_setup_table()
    assert assembler.labels["level_header"] < 0x4000, "bank-switching code must remain in fixed ROM"
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=BUILD)
    output = parser.parse_args().output_dir
    output.mkdir(parents=True, exist_ok=True)
    rom, assembler, metadata = make_rom()
    rom_path = output / "lupine3d.gb"; rom_path.write_bytes(rom)
    assembler.write_listing(output / "lupine3d.lst")
    (output / "lupine3d.sym").write_text("\n".join(f"{addr:04X} {name}" for name, addr in sorted(assembler.labels.items(), key=lambda item: item[1])) + "\n", encoding="utf-8")
    (output / "build_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Built {rom_path} ({len(rom)} bytes)")
    print(f"Engine: {metadata['engine_size']} bytes, end={metadata['engine_end']:#06x}")
    print(f"Header checksum: {metadata['header_checksum']:#04x}; global: {metadata['global_checksum']:#06x}")


if __name__ == "__main__":
    main()
