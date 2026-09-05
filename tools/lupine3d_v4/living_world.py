"""SM83 emission for the v0.6 Living World gameplay slice."""
from __future__ import annotations

from sm83 import Assembler

from .layout import *  # noqa: F401,F403
from .resources import make_entity_tiles, make_oam_shadow  # noqa: F401


def emit_level_loader(a: Assembler) -> None:
    a.label("load_level")
    a.ld_rr_label("hl", "map_data"); a.ld_rr_nn("de", MAP); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    # The resident slice consumes a fixed header but the authored source owns
    # all coordinates, profiles, spawns, door metadata, and exit placement.
    a.ld_rr_label("hl", "level_header")
    a.inc_rr("hl"); a.inc_rr("hl")  # width, height
    for address in (VRAM_PROFILE,):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.inc_rr("hl")  # palette profile (palette set 0 is currently resident)
    for address in (
        PLAYER_XL, PLAYER_XH, PLAYER_YL, PLAYER_YH, ANGLE,
        SENTINEL_XL, SENTINEL_XH, SENTINEL_YL, SENTINEL_YH,
        SENTINEL_HEALTH,
    ):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.inc_rr("hl")  # activation radius is a future multi-entity field
    for address in (EXIT_CELL_X, EXIT_CELL_Y, DOOR_COUNT):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_rr_label("hl", "door_data"); a.ld_rr_nn("de", DOOR_TABLE)
    a.ld_rr_nn("bc", MAX_DOORS * DOOR_RECORD_BYTES); a.call("copy_bc")
    a.ld_r_n("a", WORLD_MODE_LIVING); a.ld_abs_a(WORLD_MODE)
    a.ld_r_n("a", SENTINEL_DORMANT); a.ld_abs_a(SENTINEL_STATE)
    a.ld_r_n("a", 99); a.ld_abs_a(PLAYER_HEALTH)
    a.xor_r("a")
    for address in (
        SENTINEL_AI_STAMP, SENTINEL_AI_PHASE, SENTINEL_ANIM,
        SENTINEL_COOLDOWN, SENTINEL_VISIBLE, SENTINEL_OAM_USED,
        PICKUP_ACTIVE, PICKUP_COLLECTED, EXIT_ACTIVE, LEVEL_COMPLETE,
        DOOR_ACTIVE_INDEX, DOOR_ACTIVE_STATE, DOOR_ACTIVE_FRACTION,
        DOOR_ACTIVE_FLAGS, DOOR_LOOKUP_X, DOOR_LOOKUP_Y,
        OAM_DIRTY, OAM_DEFERRED,
    ):
        a.ld_abs_a(address)
    a.call("init_actors"); a.ret()


def emit_oam_system(a: Assembler) -> None:
    a.label("init_oam")
    a.ld_r_n("a", BOOT_ASSETS_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_rr_label("hl", "oam_initial"); a.ld_rr_nn("de", OAM_SHADOW); a.ld_rr_nn("bc", OAM_BYTES); a.call("copy_bc")
    a.ld_rr_label("hl", "oam_dma_stub"); a.ld_rr_nn("de", OAM_DMA_HRAM); a.ld_rr_nn("bc", OAM_DMA_STUB_BYTES); a.call("copy_bc")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT)
    for index in range(5): a.ld_abs_a(LOD_HISTORY + index)
    a.call_abs(OAM_DMA_HRAM); a.xor_r("a"); a.ld_abs_a(OAM_DIRTY); a.ret()

    a.label("publish_oam_if_budget")
    a.ld_a_abs(OAM_DIRTY); a.or_r("a"); a.ret("z")
    # One OAM DMA lasts about twenty 16-byte GDMA block times in double-speed
    # mode. Defer it when a pathological wall frame consumes the full VBlank.
    a.ld_a_abs(DYN_COUNT); a.cp_n(REPROJECT_GDMA_THRESHOLD + 1); a.jr("defer_oam_dma", "nc")
    a.label("publish_oam_packet")
    a.call_abs(OAM_DMA_HRAM)
    if ENABLE_MICRO_REPROJECTION:
        for index in range(ENTITY_OAM_COUNT):
            a.ld_a_abs(OAM_SHADOW + (ENTITY_OAM_FIRST + index) * 4 + 1); a.ld_abs_a(PUBLISHED_WORLD_X + index)
    a.xor_r("a"); a.ld_abs_a(OAM_DIRTY); a.ret()
    a.label("defer_oam_dma")
    a.ld_a_abs(OAM_DEFERRED); a.inc_r("a"); a.ld_abs_a(OAM_DEFERRED); a.ret()

    a.label("clear_entity_oam_shadow")
    a.xor_r("a")
    for index in range(ENTITY_OAM_FIRST, 40):
        a.ld_abs_a(OAM_SHADOW + index * 4)
    a.ld_rr_nn("hl", OAM_SHADOW + ENTITY_OAM_FIRST * 4); store_hl_abs(a, ENTITY_OAM_PTR_L, ENTITY_OAM_PTR_H)
    a.xor_r("a"); a.ld_abs_a(SENTINEL_OAM_USED)
    a.ld_abs_a(MASK_TILE_COUNT)
    a.ld_rr_nn("hl", WORLD_SCANLINES); a.ld_r_n("b", 144)
    a.label("clear_world_scanlines"); a.ldi_hl_a(); a.dec_r("b"); a.jr("clear_world_scanlines", "nz")
    a.ld_r_n("a", 255); a.ld_abs_a(MASK_BITS)
    a.ld_r_n("a", 1); a.ld_abs_a(OAM_DIRTY); a.ret()

    a.label("submit_oam_8x8")  # B=y, C=x, D=tile, E=attributes
    a.jp("submit_masked_oam")  # compatibility symbol; hardware now uses pairs
    # Hard allocation limit, even if later content submits more actors.
    a.ld_a_abs(SENTINEL_OAM_USED); a.cp_n(ENTITY_OAM_COUNT); a.ret("nc")
    load_hl_abs(a, ENTITY_OAM_PTR_L, ENTITY_OAM_PTR_H)
    a.ld_r_r("a", "b"); a.ldi_hl_a(); a.ld_r_r("a", "c"); a.ldi_hl_a()
    a.ld_r_r("a", "d"); a.ldi_hl_a(); a.ld_r_r("a", "e"); a.ldi_hl_a()
    store_hl_abs(a, ENTITY_OAM_PTR_L, ENTITY_OAM_PTR_H)
    a.ld_a_abs(SENTINEL_OAM_USED); a.inc_r("a"); a.ld_abs_a(SENTINEL_OAM_USED); a.ret()


def emit_door_system(a: Assembler) -> None:
    """Emit the fixed-capacity, independently stateful door runtime."""
    a.label("lookup_door_bc")  # B=x, C=y; selected record -> active scratch, A=found
    a.ld_r_r("a", "b"); a.ld_abs_a(DOOR_LOOKUP_X)
    a.ld_r_r("a", "c"); a.ld_abs_a(DOOR_LOOKUP_Y)
    for index in range(MAX_DOORS):
        next_label = f"door_lookup_{index}_next"
        base = DOOR_TABLE + index * DOOR_RECORD_BYTES
        a.ld_a_abs(DOOR_COUNT); a.cp_n(index + 1); a.jp("door_lookup_none", "c")
        a.ld_a_abs(base + DOOR_X_OFFSET); a.cp_r("b"); a.jr(next_label, "nz")
        a.ld_a_abs(base + DOOR_Y_OFFSET); a.cp_r("c"); a.jr(next_label, "nz")
        a.ld_r_n("a", index); a.ld_abs_a(DOOR_ACTIVE_INDEX)
        for source, destination in (
            (base + DOOR_STATE_OFFSET, DOOR_ACTIVE_STATE),
            (base + DOOR_FRACTION_OFFSET, DOOR_ACTIVE_FRACTION),
            (base + DOOR_FLAGS_OFFSET, DOOR_ACTIVE_FLAGS),
            (base + DOOR_ORIENTATION_OFFSET, DOOR_ACTIVE_ORIENTATION),
        ):
            a.ld_a_abs(source); a.ld_abs_a(destination)
        a.ld_r_n("a", 1); a.ret()
        a.label(next_label)
    a.label("door_lookup_none"); a.xor_r("a"); a.ret()

    a.label("store_active_door")
    for index in range(MAX_DOORS):
        next_label = f"door_store_{index}_next"
        base = DOOR_TABLE + index * DOOR_RECORD_BYTES
        a.ld_a_abs(DOOR_ACTIVE_INDEX); a.cp_n(index); a.jr(next_label, "nz")
        a.ld_a_abs(DOOR_ACTIVE_STATE); a.ld_abs_a(base + DOOR_STATE_OFFSET)
        a.ld_a_abs(DOOR_ACTIVE_FRACTION); a.ld_abs_a(base + DOOR_FRACTION_OFFSET)
        a.ret()
        a.label(next_label)
    a.ret()

    a.label("update_animated_doors")
    for index in range(MAX_DOORS):
        next_label = f"door_update_{index}_next"
        base = DOOR_TABLE + index * DOOR_RECORD_BYTES
        a.ld_a_abs(DOOR_COUNT); a.cp_n(index + 1); a.jp("door_update_all_done", "c")
        a.ld_a_abs(base + DOOR_STATE_OFFSET); a.cp_n(1); a.jr(next_label, "nz")
        a.ld_a_abs(base + DOOR_FRACTION_OFFSET); a.add_a_n(8 if FIXED_SIMULATION else 32)
        a.ld_abs_a(base + DOOR_FRACTION_OFFSET); a.jr(next_label, "nc")
        # The eighth step wraps the fraction, commits the open state, and only
        # then removes the collision/ray/LOS cell from the authoritative map.
        a.ld_r_n("a", 2); a.ld_abs_a(base + DOOR_STATE_OFFSET)
        a.ld_a_abs(base + DOOR_Y_OFFSET); a.cb("swap", "a"); a.ld_r_r("b", "a")
        a.ld_a_abs(base + DOOR_X_OFFSET); a.add_a_r("b"); a.ld_r_r("l", "a")
        a.ld_r_n("h", 0xD0); a.xor_r("a"); a.ld_hl_a()
        a.label(next_label)
    a.label("door_update_all_done"); a.ret()

    a.label("sound_locked")
    a.xor_r("a"); a.ldh_n_a(NR10)
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR11)
    a.ld_r_n("a", 0x72); a.ldh_n_a(NR12)
    a.ld_r_n("a", 0x20); a.ldh_n_a(NR13)
    a.ld_r_n("a", 0xC2); a.ldh_n_a(NR14)
    a.ret()


def emit_signed_math(a: Assembler) -> None:
    a.label("mul_s8")  # signed B*C -> signed HL
    a.ld_r_r("a", "b"); a.xor_r("c"); a.ld_abs_a(ENTITY_SIGN)
    a.ld_r_r("a", "b"); a.cb("bit", "a", 7); a.jr("mul_s8_b_ready", "z"); a.cpl(); a.inc_r("a")
    a.label("mul_s8_b_ready"); a.ld_r_r("b", "a")
    a.ld_r_r("a", "c"); a.cb("bit", "a", 7); a.jr("mul_s8_c_ready", "z"); a.cpl(); a.inc_r("a")
    a.label("mul_s8_c_ready"); a.ld_r_r("c", "a"); a.call("mul_u8")
    a.ld_a_abs(ENTITY_SIGN); a.cb("bit", "a", 7); a.ret("z")
    a.ld_r_r("a", "l"); a.cpl(); a.add_a_n(1); a.ld_r_r("l", "a")
    a.ld_r_r("a", "h"); a.cpl(); a.adc_a_n(0); a.ld_r_r("h", "a"); a.ret()

    a.label("negate_hl")
    a.ld_r_r("a", "l"); a.cpl(); a.add_a_n(1); a.ld_r_r("l", "a")
    a.ld_r_r("a", "h"); a.cpl(); a.adc_a_n(0); a.ld_r_r("h", "a"); a.ret()


def _emit_q4_delta(a: Assembler, prefix: str, entity_lo: int, entity_hi: int,
                   player_lo: int, player_hi: int, destination: int) -> None:
    a.ld_a_abs(entity_lo); a.ld_r_r("l", "a"); a.ld_a_abs(entity_hi); a.ld_r_r("h", "a")
    a.ld_a_abs(player_lo); a.ld_r_r("b", "a"); a.ld_r_r("a", "l"); a.sub_r("b"); a.ld_r_r("l", "a")
    a.ld_a_abs(player_hi); a.ld_r_r("b", "a"); a.ld_r_r("a", "h"); a.sbc_a_r("b"); a.ld_r_r("h", "a")
    for _ in range(4):
        a.cb("sra", "h"); a.cb("rr", "l")
    # Only the signed-eight-bit Q4 range is projected. Farther actors are
    # dormant and consume no OAM until the player enters their scene cell.
    a.ld_r_r("a", "h"); a.or_r("a"); a.jr(f"{prefix}_positive", "z")
    a.cp_n(0xFF); a.jp("project_entity_hidden", "nz")
    a.ld_r_r("a", "l"); a.cb("bit", "a", 7); a.jp("project_entity_hidden", "z"); a.jr(f"{prefix}_store")
    a.label(f"{prefix}_positive")
    a.ld_r_r("a", "l"); a.cb("bit", "a", 7); a.jp("project_entity_hidden", "nz")
    a.label(f"{prefix}_store"); a.ld_r_r("a", "l"); a.ld_abs_a(destination)


def emit_entity_projection(a: Assembler) -> None:
    a.label("project_sentinel")
    for source, destination in (
        (SENTINEL_XL, ENTITY_WORLD_XL), (SENTINEL_XH, ENTITY_WORLD_XH),
        (SENTINEL_YL, ENTITY_WORLD_YL), (SENTINEL_YH, ENTITY_WORLD_YH),
    ):
        a.ld_a_abs(source); a.ld_abs_a(destination)
    a.label("project_entity")
    a.xor_r("a"); a.ld_abs_a(SENTINEL_VISIBLE)
    a.ld_r_n("a", 255); a.ld_abs_a(SENTINEL_SCREEN_X)
    _emit_q4_delta(a, "entity_dx", ENTITY_WORLD_XL, ENTITY_WORLD_XH, PLAYER_XL, PLAYER_XH, ENTITY_DX)
    _emit_q4_delta(a, "entity_dy", ENTITY_WORLD_YL, ENTITY_WORLD_YH, PLAYER_YL, PLAYER_YH, ENTITY_DY)
    # Camera basis uses the exact 256-entry signed movement vectors (scale 64).
    a.ld_a_abs(ANGLE); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "step_dx"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ENTITY_COS)
    a.ld_a_abs(ANGLE); a.ld_r_r("e", "a"); a.ld_rr_label("hl", "step_dy"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ENTITY_SIN)
    # Forward = (dx*cos + dy*sin) / 64.
    a.ld_a_abs(ENTITY_DX); a.ld_r_r("b", "a"); a.ld_a_abs(ENTITY_COS); a.ld_r_r("c", "a"); a.call("mul_s8")
    a.ld_r_r("a", "l"); a.ld_abs_a(ENTITY_TMP_L); a.ld_r_r("a", "h"); a.ld_abs_a(ENTITY_TMP_H)
    a.ld_a_abs(ENTITY_DY); a.ld_r_r("b", "a"); a.ld_a_abs(ENTITY_SIN); a.ld_r_r("c", "a"); a.call("mul_s8")
    a.ld_a_abs(ENTITY_TMP_L); a.ld_r_r("e", "a"); a.ld_a_abs(ENTITY_TMP_H); a.ld_r_r("d", "a"); a.add_hl_rr("de")
    for _ in range(6): a.cb("sra", "h"); a.cb("rr", "l")
    a.ld_r_r("a", "h"); a.or_r("a"); a.jp("project_entity_hidden", "nz")
    a.ld_r_r("a", "l"); a.cp_n(5); a.jp("project_entity_hidden", "c"); a.cb("bit", "a", 7); a.jp("project_entity_hidden", "nz"); a.ld_abs_a(ENTITY_FORWARD)
    # Lateral = (-dx*sin + dy*cos) / 64.
    a.ld_a_abs(ENTITY_DX); a.ld_r_r("b", "a"); a.ld_a_abs(ENTITY_SIN); a.ld_r_r("c", "a"); a.call("mul_s8"); a.call("negate_hl")
    a.ld_r_r("a", "l"); a.ld_abs_a(ENTITY_TMP_L); a.ld_r_r("a", "h"); a.ld_abs_a(ENTITY_TMP_H)
    a.ld_a_abs(ENTITY_DY); a.ld_r_r("b", "a"); a.ld_a_abs(ENTITY_COS); a.ld_r_r("c", "a"); a.call("mul_s8")
    a.ld_a_abs(ENTITY_TMP_L); a.ld_r_r("e", "a"); a.ld_a_abs(ENTITY_TMP_H); a.ld_r_r("d", "a"); a.add_hl_rr("de")
    for _ in range(6): a.cb("sra", "h"); a.cb("rr", "l")
    a.ld_r_r("a", "h"); a.or_r("a"); a.jr("entity_lateral_positive", "z"); a.cp_n(0xFF); a.jp("project_entity_hidden", "nz")
    a.label("entity_lateral_positive"); a.ld_r_r("a", "l"); a.ld_abs_a(ENTITY_LATERAL)
    # Share the wall camera's focal length, rounded to the nearest pixel.
    a.ld_a_abs(ENTITY_FORWARD); a.add_a_r("a"); a.ld_abs_a(SENTINEL_DEPTH)
    a.ld_a_abs(ENTITY_LATERAL); a.ld_r_r("d", "a"); a.cb("bit", "a", 7); a.jr("entity_lateral_abs_ready", "z"); a.cpl(); a.inc_r("a")
    a.label("entity_lateral_abs_ready"); a.cp_n(128); a.jp("project_entity_hidden", "nc")
    # Product LUT requires C <=127; focal length belongs in B, not C.
    a.ld_r_r("c", "a"); a.ld_r_n("b", CAMERA_FOCAL_PIXELS); a.call("mul_u8")
    a.ld_a_abs(ENTITY_FORWARD); a.ld_r_r("b", "a"); a.call("div_u16_u8_sat")
    a.cp_n(88); a.jp("project_entity_hidden", "nc"); a.ld_r_r("b", "a")
    a.ld_a_abs(ENTITY_LATERAL); a.cb("bit", "a", 7); a.ld_r_n("a", 80); a.jr("entity_screen_right", "z")
    a.sub_r("b"); a.jr("entity_screen_ready")
    a.label("entity_screen_right"); a.add_a_r("b")
    a.label("entity_screen_ready"); a.ld_abs_a(SENTINEL_SCREEN_X)
    a.ld_a_abs(DECAL_PROJECTING); a.or_r("a"); a.jr("entity_project_foot", "nz")
    a.call("choose_entity_lod")
    a.label("entity_project_foot")
    # Wall projection places the floor at horizon + 30/depth-in-tiles.
    # Forward is Q4, so project the billboard's feet using 480/forward.
    a.ld_rr_nn("hl", 480); a.ld_a_abs(ENTITY_FORWARD); a.ld_r_r("b", "a"); a.call("div_u16_u8_sat")
    a.add_a_n(48); a.cp_n(97); a.jr("entity_foot_in_view", "c"); a.ld_r_n("a", 96)
    a.label("entity_foot_in_view"); a.add_a_n(16); a.ld_abs_a(ENTITY_FOOT_Y)
    a.ld_a_abs(DECAL_PROJECTING); a.or_r("a"); a.jr("entity_project_occlusion", "z")
    a.ld_r_n("a", 1); a.ld_abs_a(SENTINEL_VISIBLE); a.ret()
    a.label("entity_project_occlusion")

    # Coarse 8-pixel strip occlusion against authoritative two-pixel wall depth.
    a.ld_a_abs(SENTINEL_LOD); a.cp_n(2); a.jr("project_near_visibility", "nz")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.call("entity_column_visible"); a.ld_abs_a(ENTITY_SCREEN_LEFT); a.ld_abs_a(ENTITY_SCREEN_RIGHT); a.or_r("a"); a.jr("project_visibility_store")
    a.label("project_near_visibility")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.sub_n(4); a.call("entity_column_visible"); a.ld_abs_a(ENTITY_SCREEN_LEFT)
    a.ld_a_abs(SENTINEL_SCREEN_X); a.add_a_n(4); a.call("entity_column_visible"); a.ld_abs_a(ENTITY_SCREEN_RIGHT)
    a.ld_r_r("b", "a"); a.ld_a_abs(ENTITY_SCREEN_LEFT); a.or_r("b")
    a.label("project_visibility_store"); a.or_r("a"); a.jr("project_visibility_zero", "z"); a.ld_r_n("a", 1)
    a.label("project_visibility_zero"); a.ld_abs_a(SENTINEL_VISIBLE); a.ret()
    a.label("project_entity_hidden"); a.xor_r("a"); a.ld_abs_a(SENTINEL_VISIBLE); a.ret()

    a.label("entity_column_visible")  # input centre X of one 8-pixel strip
    # Test all four two-pixel wall samples covered by the OAM strip. A strip
    # is omitted only when it is fully behind walls; mixed strips remain a
    # deliberate coarse-clipping case until masked cels are introduced.
    a.sub_n(4); a.ld_abs_a(ENTITY_TMP_L); a.ld_r_n("a", 8); a.ld_abs_a(ENTITY_TMP_H)
    a.xor_r("a"); a.ld_abs_a(MASK_BITS)
    a.label("entity_strip_depth_loop")
    a.ld_a_abs(MASK_BITS); a.add_a_r("a"); a.ld_abs_a(MASK_BITS)
    a.ld_a_abs(ENTITY_TMP_L); a.cp_n(PHYSICAL_COLUMNS); a.jr("entity_strip_next", "nc")
    a.cb("srl", "a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_DEPTH); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_DEPTH); a.cp_r("b"); a.jr("entity_strip_next", "nc")
    a.ld_a_abs(MASK_BITS); a.or_n(1); a.ld_abs_a(MASK_BITS)
    a.label("entity_strip_next")
    a.ld_a_abs(ENTITY_TMP_L); a.inc_r("a"); a.ld_abs_a(ENTITY_TMP_L)
    a.ld_a_abs(ENTITY_TMP_H); a.dec_r("a"); a.ld_abs_a(ENTITY_TMP_H); a.jr("entity_strip_depth_loop", "nz")
    a.ld_a_abs(MASK_BITS); a.ret()


def emit_entity_renderer(a: Assembler) -> None:
    a.label("render_entities")
    a.call("clear_entity_oam_shadow")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(VRAM_PROFILE); a.cp_n(VRAM_PROFILE_ENTITY); a.ret("nz")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.jr("render_dead_world", "z")
    a.call("render_sentinel_actor"); a.jr("render_world_exit")
    a.label("render_dead_world"); a.call("render_dropped_pickup")
    a.label("render_world_exit"); a.call("render_exit_beacon"); a.ret()

    a.label("render_sentinel_actor")
    a.call("project_sentinel"); a.ld_a_abs(SENTINEL_VISIBLE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(SENTINEL_LOD); a.or_r("a"); a.jr("render_sentinel_near", "z")
    # Far LOD: one 8x16 column represented by two 8x8 objects.
    a.ld_a_abs(SENTINEL_ANIM); a.and_n(1); a.add_a_r("a"); a.add_a_n(SENTINEL_FAR_TILE_BASE); a.ld_abs_a(ENTITY_TILE_BASE_STATE)
    for row in range(2):
        a.ld_a_abs(ENTITY_FOOT_Y); a.sub_n(16 - row * 8); a.ld_r_r("b", "a")
        a.ld_a_abs(SENTINEL_SCREEN_X); a.add_a_n(4); a.ld_r_r("c", "a")
        a.ld_a_abs(ENTITY_TILE_BASE_STATE)
        if row: a.inc_r("a")
        a.ld_r_r("d", "a"); a.ld_r_n("e", 0x09); a.call("submit_oam_8x8")
    a.ret()

    a.label("render_sentinel_near")
    a.ld_a_abs(SENTINEL_ANIM); a.and_n(3)
    for _ in range(3): a.add_a_r("a")
    a.add_a_n(SENTINEL_NEAR_TILE_BASE); a.ld_abs_a(ENTITY_TILE_BASE_STATE)
    for col, visible_address in ((0, ENTITY_SCREEN_LEFT), (1, ENTITY_SCREEN_RIGHT)):
        skip = f"render_near_column_{col}_skip"
        a.ld_a_abs(visible_address); a.or_r("a"); a.jr(skip, "z")
        for row in range(4):
            a.ld_a_abs(ENTITY_FOOT_Y); a.sub_n(32 - row * 8); a.ld_r_r("b", "a")
            a.ld_a_abs(SENTINEL_SCREEN_X)
            if col == 1: a.add_a_n(8)
            a.ld_r_r("c", "a")
            a.ld_a_abs(ENTITY_TILE_BASE_STATE); a.add_a_n(row * 2 + col); a.ld_r_r("d", "a")
            a.ld_r_n("e", 0x09); a.call("submit_oam_8x8")
        a.label(skip)
    a.ret()

    a.label("render_dropped_pickup")
    a.ld_a_abs(PICKUP_ACTIVE); a.or_r("a"); a.ret("z")
    a.call("project_sentinel"); a.ld_a_abs(SENTINEL_VISIBLE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(ENTITY_FOOT_Y); a.sub_n(8); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.add_a_n(4); a.ld_r_r("c", "a")
    a.ld_r_n("d", PICKUP_TILE); a.ld_r_n("e", 0x09); a.call("submit_oam_8x8"); a.ret()

    a.label("render_exit_beacon")
    a.ld_a_abs(EXIT_ACTIVE); a.or_r("a"); a.ret("z")
    a.ld_r_n("a", 0x80); a.ld_abs_a(ENTITY_WORLD_XL); a.ld_abs_a(ENTITY_WORLD_YL)
    a.ld_a_abs(EXIT_CELL_X); a.ld_abs_a(ENTITY_WORLD_XH)
    a.ld_a_abs(EXIT_CELL_Y); a.ld_abs_a(ENTITY_WORLD_YH)
    a.call("project_entity"); a.ld_a_abs(SENTINEL_VISIBLE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(SENTINEL_AI_PHASE); a.and_n(1); a.add_a_n(EXIT_BEACON_TILE); a.ld_r_r("d", "a")
    a.ld_a_abs(SENTINEL_LOD); a.or_r("a"); a.jr("render_exit_beacon_far", "nz")
    # Near the exit, mirror the same chevron tile into a 16x16 illuminated
    # panel. This spends OAM rather than scarce tile IDs and gives the goal a
    # strong approach cue without adding screen-space HUD text.
    for row in range(2):
        for col in range(2):
            a.ld_r_n("b", 68 + row * 8)
            a.ld_a_abs(SENTINEL_SCREEN_X)
            if col: a.add_a_n(8)
            a.ld_r_r("c", "a")
            a.ld_a_abs(SENTINEL_AI_PHASE); a.and_n(1); a.add_a_n(EXIT_BEACON_TILE); a.ld_r_r("d", "a")
            a.ld_r_n("e", 0x09 | (0x20 if col else 0) | (0x40 if row else 0))
            a.call("submit_oam_8x8")
    a.ret()
    a.label("render_exit_beacon_far")
    a.ld_r_n("b", 76); a.ld_a_abs(SENTINEL_SCREEN_X); a.add_a_n(4); a.ld_r_r("c", "a")
    a.ld_r_n("e", 0x09); a.call("submit_oam_8x8"); a.ret()


def emit_line_of_sight(a: Assembler) -> None:
    a.label("sentinel_line_of_sight")
    # Cell-space Bresenham traversal. Every visited cell is checked against
    # the exact active WRAM grid; the player's destination cell is accepted.
    a.ld_a_abs(SENTINEL_XH); a.ld_abs_a(LOS_X); a.ld_r_r("b", "a")
    a.ld_a_abs(PLAYER_XH); a.sub_r("b"); a.ld_r_n("c", 1); a.jr("los_dx_positive", "nc"); a.cpl(); a.inc_r("a"); a.ld_r_n("c", 0xFF)
    a.label("los_dx_positive"); a.ld_abs_a(LOS_DX); a.ld_r_r("a", "c"); a.ld_abs_a(LOS_SX)
    a.ld_a_abs(SENTINEL_YH); a.ld_abs_a(LOS_Y); a.ld_r_r("b", "a")
    a.ld_a_abs(PLAYER_YH); a.sub_r("b"); a.ld_r_n("c", 1); a.jr("los_dy_positive", "nc"); a.cpl(); a.inc_r("a"); a.ld_r_n("c", 0xFF)
    a.label("los_dy_positive"); a.ld_abs_a(LOS_DY); a.ld_r_r("a", "c"); a.ld_abs_a(LOS_SY)
    # Exact subcell line query from player to Sentinel. The same grid and
    # sliding-panel intersection routine is used by rendering and hitscan.
    for entity, player, target in ((SENTINEL_XL, PLAYER_XL, Q14_X), (SENTINEL_YL, PLAYER_YL, Q14_Y)):
        a.ld_a_abs(player); a.ld_r_r("b", "a"); a.ld_a_abs(entity); a.sub_r("b"); a.ld_abs_a(target)
        a.ld_a_abs(player + 1); a.ld_r_r("b", "a"); a.ld_a_abs(entity + 1); a.sbc_a_r("b"); a.ld_abs_a(target + 1)
    a.xor_r("a"); a.ld_r_r("b", "a")
    for address in (Q14_X, Q14_X + 1, Q14_Y, Q14_Y + 1):
        a.ld_a_abs(address); a.or_r("b"); a.ld_r_r("b", "a")
    a.jp("los_visible", "z")
    a.call("prepare_frame_boundaries"); a.call("q14_vector_cast")
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.ld_rr_nn("hl", Q14_X); a.jr("los_target_component", "z"); a.ld_rr_nn("hl", Q14_Y)
    a.label("los_target_component")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(DDA_DIST_L); a.sub_r("e"); a.ld_a_abs(DDA_DIST_H); a.sbc_a_r("d")
    a.jp("los_blocked", "c"); a.jp("los_visible")
    a.ld_a_abs(LOS_DX); a.add_a_n(128); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_DY); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.sub_r("c"); a.ld_abs_a(LOS_ERR)
    a.ld_r_n("a", 32); a.ld_abs_a(LOS_COUNT)
    a.label("los_loop")
    a.ld_a_abs(LOS_X); a.ld_r_r("b", "a"); a.ld_a_abs(PLAYER_XH); a.cp_r("b"); a.jr("los_not_at_player", "nz")
    a.ld_a_abs(LOS_Y); a.ld_r_r("b", "a"); a.ld_a_abs(PLAYER_YH); a.cp_r("b"); a.jr("los_not_at_player", "nz")
    a.ld_r_n("a", 1); a.ld_abs_a(LOS_RESULT); a.ret()
    a.label("los_not_at_player")
    # Biased E2 = 2*(err-128)+128.
    a.ld_a_abs(LOS_ERR); a.add_a_r("a"); a.sub_n(128); a.ld_abs_a(LOS_E2)
    # if e2 >= -dy, advance X and subtract dy from error.
    a.ld_a_abs(LOS_DY); a.ld_r_r("b", "a"); a.ld_r_n("a", 128); a.sub_r("b"); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_E2); a.cp_r("b"); a.jr("los_skip_x", "c")
    a.ld_a_abs(LOS_ERR); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_DY); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.sub_r("c"); a.ld_abs_a(LOS_ERR)
    a.ld_a_abs(LOS_SX); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_X); a.add_a_r("b"); a.ld_abs_a(LOS_X)
    a.label("los_skip_x")
    # if e2 <= dx, advance Y and add dx to error.
    a.ld_a_abs(LOS_DX); a.add_a_n(128); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_E2); a.cp_r("b"); a.jr("los_skip_y", "nc")
    a.ld_a_abs(LOS_ERR); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_DX); a.add_a_r("b"); a.ld_abs_a(LOS_ERR)
    a.ld_a_abs(LOS_SY); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_Y); a.add_a_r("b"); a.ld_abs_a(LOS_Y)
    a.label("los_skip_y")
    # Destination is allowed; every earlier solid cell blocks sight.
    a.ld_a_abs(LOS_X); a.ld_r_r("b", "a"); a.ld_a_abs(PLAYER_XH); a.cp_r("b"); a.jr("los_check_map", "nz")
    a.ld_a_abs(LOS_Y); a.ld_r_r("b", "a"); a.ld_a_abs(PLAYER_YH); a.cp_r("b"); a.jr("los_visible", "z")
    a.label("los_check_map")
    a.ld_a_abs(LOS_Y); a.cb("swap", "a"); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_X); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0); a.ld_a_hl(); a.or_r("a"); a.jr("los_blocked", "nz")
    a.ld_a_abs(LOS_COUNT); a.dec_r("a"); a.ld_abs_a(LOS_COUNT); a.jp("los_loop", "nz")
    a.label("los_blocked"); a.xor_r("a"); a.ld_abs_a(LOS_RESULT); a.ret()
    a.label("los_visible"); a.ld_r_n("a", 1); a.ld_abs_a(LOS_RESULT); a.ret()


def emit_world_update(a: Assembler) -> None:
    a.label("update_world")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.ret("z")
    a.call("update_animated_doors"); a.call("collect_pickup_and_exit")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.ret("z")
    a.ld_r_n("a", 4); a.ld_abs_a(AI_CATCHUP_BUDGET)
    a.label("ai_catchup_loop")
    a.ld_a_abs(INPUT_SAMPLE_COUNT); a.ld_r_r("b", "a"); a.ld_a_abs(SENTINEL_AI_STAMP); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.sub_r("c"); a.cp_n(AI_TICK_INTERVAL); a.ret("c")
    # Preserve fractional and excess ticks. At most four AI steps per render
    # prevents a backlog from monopolising the CPU; remaining debt is retained.
    a.ld_r_r("a", "c"); a.add_a_n(AI_TICK_INTERVAL); a.ld_abs_a(SENTINEL_AI_STAMP)
    a.call("sentinel_ai_tick")
    a.ld_a_abs(AI_CATCHUP_BUDGET); a.dec_r("a"); a.ld_abs_a(AI_CATCHUP_BUDGET); a.jr("ai_catchup_loop", "nz"); a.ret()
    a.label("sentinel_ai_tick")
    a.ld_a_abs(SENTINEL_COOLDOWN); a.or_r("a"); a.jr("ai_cooldown_done", "z"); a.dec_r("a"); a.ld_abs_a(SENTINEL_COOLDOWN)
    a.label("ai_cooldown_done")
    a.ld_a_abs(SENTINEL_AI_PHASE); a.inc_r("a"); a.ld_abs_a(SENTINEL_AI_PHASE)
    a.call("sentinel_line_of_sight")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DORMANT); a.jr("ai_not_dormant", "nz")
    a.ld_a_abs(SENTINEL_AI_PHASE); a.cp_n(2); a.ret("c"); a.ld_r_n("a", SENTINEL_PATROL); a.ld_abs_a(SENTINEL_STATE)
    a.label("ai_not_dormant")
    a.ld_a_abs(LOS_RESULT); a.or_r("a"); a.jr("ai_patrol", "z")
    a.ld_a_abs(LOS_DX); a.cp_n(2); a.jr("ai_chase", "nc"); a.ld_a_abs(LOS_DY); a.cp_n(2); a.jr("ai_chase", "nc")
    a.ld_r_n("a", SENTINEL_ATTACK); a.ld_abs_a(SENTINEL_STATE)
    a.ld_a_abs(SENTINEL_COOLDOWN); a.or_r("a"); a.jr("ai_animate", "nz")
    a.ld_r_n("a", 8); a.ld_abs_a(SENTINEL_COOLDOWN)
    a.ld_a_abs(PLAYER_HEALTH); a.sub_n(8); a.jr("ai_health_store", "nc"); a.xor_r("a")
    a.label("ai_health_store"); a.ld_abs_a(PLAYER_HEALTH); a.jr("ai_animate")
    a.label("ai_chase"); a.ld_r_n("a", SENTINEL_CHASE); a.ld_abs_a(SENTINEL_STATE); a.call("sentinel_chase_step"); a.jr("ai_animate")
    a.label("ai_patrol"); a.ld_r_n("a", SENTINEL_PATROL); a.ld_abs_a(SENTINEL_STATE); a.call("sentinel_patrol_step")
    a.label("ai_animate")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_ATTACK); a.ld_r_n("a", 2); a.jr("ai_animation_store", "z")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_HURT); a.ld_r_n("a", 3); a.jr("ai_animation_store", "z")
    a.ld_a_abs(SENTINEL_AI_PHASE); a.and_n(1)
    a.label("ai_animation_store"); a.ld_abs_a(SENTINEL_ANIM); a.ret()

    a.label("sentinel_patrol_step")
    a.ld_a_abs(SENTINEL_AI_PHASE); a.and_n(8); a.ld_a_abs(SENTINEL_YL); a.jr("patrol_step_up", "z")
    a.sub_n(4); a.ld_abs_a(SENTINEL_YL); a.ret()
    a.label("patrol_step_up"); a.add_a_n(4); a.ld_abs_a(SENTINEL_YL); a.ret()

    a.label("sentinel_chase_step")
    # Move along the dominant cell delta. The small Q8 step and boundary map
    # test keep the actor inside empty cells without a general physics system.
    a.ld_a_abs(LOS_DX); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_DY); a.cp_r("b"); a.jr("sentinel_chase_y", "nc")
    a.ld_a_abs(LOS_SX); a.cp_n(1); a.jr("sentinel_chase_x_negative", "nz")
    a.ld_a_abs(SENTINEL_XL); a.add_a_n(8); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_XH); a.adc_a_n(0); a.ld_abs_a(v1.CAND_H); a.jr("sentinel_chase_x_test")
    a.label("sentinel_chase_x_negative")
    a.ld_a_abs(SENTINEL_XL); a.sub_n(8); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_XH); a.sbc_a_n(0); a.ld_abs_a(v1.CAND_H)
    a.label("sentinel_chase_x_test")
    for source, dest in ((v1.CAND_L, COLLISION_X), (v1.CAND_H, COLLISION_X + 1), (SENTINEL_YL, COLLISION_Y), (SENTINEL_YH, COLLISION_Y + 1)):
        a.ld_a_abs(source); a.ld_abs_a(dest)
    a.ld_a_abs(v1.CAND_H); a.ld_r_r("b", "a"); a.ld_a_abs(SENTINEL_YH); a.ld_r_r("c", "a"); a.call("collision_cell_bc"); a.or_r("a"); a.ret("nz")
    a.ld_a_abs(v1.CAND_L); a.ld_abs_a(SENTINEL_XL); a.ld_a_abs(v1.CAND_H); a.ld_abs_a(SENTINEL_XH); a.ret()
    a.label("sentinel_chase_y")
    a.ld_a_abs(LOS_SY); a.cp_n(1); a.jr("sentinel_chase_y_negative", "nz")
    a.ld_a_abs(SENTINEL_YL); a.add_a_n(8); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_YH); a.adc_a_n(0); a.ld_abs_a(v1.CAND_H); a.jr("sentinel_chase_y_test")
    a.label("sentinel_chase_y_negative")
    a.ld_a_abs(SENTINEL_YL); a.sub_n(8); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_YH); a.sbc_a_n(0); a.ld_abs_a(v1.CAND_H)
    a.label("sentinel_chase_y_test")
    for source, dest in ((SENTINEL_XL, COLLISION_X), (SENTINEL_XH, COLLISION_X + 1), (v1.CAND_L, COLLISION_Y), (v1.CAND_H, COLLISION_Y + 1)):
        a.ld_a_abs(source); a.ld_abs_a(dest)
    a.ld_a_abs(v1.CAND_H); a.ld_r_r("c", "a"); a.ld_a_abs(SENTINEL_XH); a.ld_r_r("b", "a"); a.call("collision_cell_bc"); a.or_r("a"); a.ret("nz")
    a.ld_a_abs(v1.CAND_L); a.ld_abs_a(SENTINEL_YL); a.ld_a_abs(v1.CAND_H); a.ld_abs_a(SENTINEL_YH); a.ret()

    a.label("collect_pickup_and_exit")
    a.ld_a_abs(PICKUP_ACTIVE); a.or_r("a"); a.jr("check_level_exit", "z")
    a.ld_a_abs(PLAYER_XH); a.ld_r_r("b", "a"); a.ld_a_abs(SENTINEL_XH); a.cp_r("b"); a.jr("check_level_exit", "nz")
    a.ld_a_abs(PLAYER_YH); a.ld_r_r("b", "a"); a.ld_a_abs(SENTINEL_YH); a.cp_r("b"); a.jr("check_level_exit", "nz")
    a.xor_r("a"); a.ld_abs_a(PICKUP_ACTIVE); a.ld_r_n("a", 1); a.ld_abs_a(PICKUP_COLLECTED)
    a.ld_a_abs(PLAYER_HEALTH); a.add_a_n(ACTIVE_LEVEL.pickups[0].value); a.jr("pickup_health_store", "nc"); a.ld_r_n("a", 0xFF)
    a.label("pickup_health_store"); a.ld_abs_a(PLAYER_HEALTH)
    a.label("check_level_exit")
    a.ld_a_abs(EXIT_ACTIVE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(PLAYER_XH); a.ld_r_r("b", "a"); a.ld_a_abs(EXIT_CELL_X); a.cp_r("b"); a.ret("nz")
    a.ld_a_abs(PLAYER_YH); a.ld_r_r("b", "a"); a.ld_a_abs(EXIT_CELL_Y); a.cp_r("b"); a.ret("nz")
    a.ld_r_n("a", 1); a.ld_abs_a(LEVEL_COMPLETE); a.ret()

    a.label("player_fire_single")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.ret("z")
    # Recompute aim from the current pose. Cached visibility belongs to the
    # previous render (and may even have been overwritten by the exit beacon).
    a.call("project_sentinel")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.cp_n(72); a.ret("c"); a.cp_n(89); a.ret("nc")
    # An exact grid traversal along the current camera centre supplies the
    # occluder; never use last frame's interpolated wall-depth buffer to fire.
    a.call("prepare_frame_boundaries")
    a.ld_a_abs(ANGLE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(RAY_PLAYER_SHIFT): a.add_hl_rr("hl")
    store_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_r_n("a", RAY_VECTOR_SCALE); a.ld_abs_a(DDA_CORRECTION)
    a.ld_r_n("a", 240); a.ld_abs_a(Q14_RECORD)
    a.call("cast_one_v2")
    a.ld_a_abs(DEPTH_RESULT); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_DEPTH); a.cp_r("b"); a.ret("nc")
    a.ld_a_abs(SENTINEL_HEALTH); a.dec_r("a"); a.ld_abs_a(SENTINEL_HEALTH); a.jr("sentinel_survived_hit", "nz")
    a.ld_r_n("a", SENTINEL_DEAD); a.ld_abs_a(SENTINEL_STATE)
    a.ld_r_n("a", 1); a.ld_abs_a(PICKUP_ACTIVE); a.ld_abs_a(EXIT_ACTIVE); a.ret()
    a.label("sentinel_survived_hit"); a.ld_r_n("a", SENTINEL_HURT); a.ld_abs_a(SENTINEL_STATE); a.ld_r_n("a", 3); a.ld_abs_a(SENTINEL_ANIM); a.ret()


def emit_movement_v6(a: Assembler) -> None:
    a.label("map_cell_bc")  # B=x cell, C=y cell -> A material
    a.ld_r_r("a", "c"); a.cb("swap", "a"); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0); a.ld_a_hl(); a.ret()

    a.label("move_player")
    a.ld_abs_a(v1.MOVE_ANGLE)
    # X candidate and signed delta.
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "move_dx"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(MOVE_DELTA); a.ld_r_r("b", "a")
    a.ld_r_n("c", 0); a.cb("bit", "b", 7); a.jr("move6_x_sign_ready", "z"); a.dec_r("c")
    a.label("move6_x_sign_ready")
    a.ld_a_abs(PLAYER_XL); a.add_a_r("b"); a.ld_abs_a(v1.CAND_L); a.ld_a_abs(PLAYER_XH); a.adc_a_r("c"); a.ld_abs_a(v1.CAND_H)
    for source, dest in ((v1.CAND_L, COLLISION_X), (v1.CAND_H, COLLISION_X + 1), (PLAYER_YL, COLLISION_Y), (PLAYER_YH, COLLISION_Y + 1)):
        a.ld_a_abs(source); a.ld_abs_a(dest)
    # Leading X edge.
    a.ld_a_abs(MOVE_DELTA); a.cb("bit", "a", 7); a.jr("move6_x_edge_negative", "nz")
    a.ld_a_abs(v1.CAND_L); a.add_a_n(PLAYER_RADIUS_Q8); a.ld_a_abs(v1.CAND_H); a.adc_a_n(0); a.jr("move6_x_edge_ready")
    a.label("move6_x_edge_negative"); a.ld_a_abs(v1.CAND_L); a.sub_n(PLAYER_RADIUS_Q8); a.ld_a_abs(v1.CAND_H); a.sbc_a_n(0)
    a.label("move6_x_edge_ready"); a.ld_abs_a(COLLIDE_EDGE)
    # Y radius cells.
    a.ld_a_abs(PLAYER_YL); a.sub_n(PLAYER_RADIUS_Q8); a.ld_a_abs(PLAYER_YH); a.sbc_a_n(0); a.ld_abs_a(COLLIDE_LOW)
    a.ld_a_abs(PLAYER_YL); a.add_a_n(PLAYER_RADIUS_Q8); a.ld_a_abs(PLAYER_YH); a.adc_a_n(0); a.ld_abs_a(COLLIDE_HIGH)
    for address, skip in ((COLLIDE_LOW, "move6_x_blocked"), (COLLIDE_HIGH, "move6_x_blocked")):
        a.ld_a_abs(COLLIDE_EDGE); a.ld_r_r("b", "a"); a.ld_a_abs(address); a.ld_r_r("c", "a"); a.call("collision_cell_bc"); a.or_r("a"); a.jr(skip, "nz")
    a.ld_a_abs(v1.CAND_L); a.ld_abs_a(PLAYER_XL); a.ld_a_abs(v1.CAND_H); a.ld_abs_a(PLAYER_XH)
    a.label("move6_x_blocked")
    # Y candidate and leading edge.
    a.ld_a_abs(v1.MOVE_ANGLE); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "move_dy"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(MOVE_DELTA); a.ld_r_r("b", "a")
    a.ld_r_n("c", 0); a.cb("bit", "b", 7); a.jr("move6_y_sign_ready", "z"); a.dec_r("c")
    a.label("move6_y_sign_ready")
    a.ld_a_abs(PLAYER_YL); a.add_a_r("b"); a.ld_abs_a(v1.CAND_L); a.ld_a_abs(PLAYER_YH); a.adc_a_r("c"); a.ld_abs_a(v1.CAND_H)
    for source, dest in ((PLAYER_XL, COLLISION_X), (PLAYER_XH, COLLISION_X + 1), (v1.CAND_L, COLLISION_Y), (v1.CAND_H, COLLISION_Y + 1)):
        a.ld_a_abs(source); a.ld_abs_a(dest)
    a.ld_a_abs(MOVE_DELTA); a.cb("bit", "a", 7); a.jr("move6_y_edge_negative", "nz")
    a.ld_a_abs(v1.CAND_L); a.add_a_n(PLAYER_RADIUS_Q8); a.ld_a_abs(v1.CAND_H); a.adc_a_n(0); a.jr("move6_y_edge_ready")
    a.label("move6_y_edge_negative"); a.ld_a_abs(v1.CAND_L); a.sub_n(PLAYER_RADIUS_Q8); a.ld_a_abs(v1.CAND_H); a.sbc_a_n(0)
    a.label("move6_y_edge_ready"); a.ld_abs_a(COLLIDE_EDGE)
    a.ld_a_abs(PLAYER_XL); a.sub_n(PLAYER_RADIUS_Q8); a.ld_a_abs(PLAYER_XH); a.sbc_a_n(0); a.ld_abs_a(COLLIDE_LOW)
    a.ld_a_abs(PLAYER_XL); a.add_a_n(PLAYER_RADIUS_Q8); a.ld_a_abs(PLAYER_XH); a.adc_a_n(0); a.ld_abs_a(COLLIDE_HIGH)
    for address, skip in ((COLLIDE_LOW, "move6_y_blocked"), (COLLIDE_HIGH, "move6_y_blocked")):
        a.ld_a_abs(address); a.ld_r_r("b", "a"); a.ld_a_abs(COLLIDE_EDGE); a.ld_r_r("c", "a"); a.call("collision_cell_bc"); a.or_r("a"); a.jr(skip, "nz")
    a.ld_a_abs(v1.CAND_L); a.ld_abs_a(PLAYER_YL); a.ld_a_abs(v1.CAND_H); a.ld_abs_a(PLAYER_YH)
    a.label("move6_y_blocked"); a.ret()

    a.label("open_door")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.jr("open_door_legacy", "z")
    # Keep the proven two-quarter-step interaction reach.
    a.ld_a_abs(ANGLE); a.call("ray_setup"); a.ld_r_n("a", 2); a.ld_abs_a(v1.DOOR_COUNT)
    a.label("open_door6_advance"); a.call("ray_advance"); a.ld_a_abs(v1.DOOR_COUNT); a.dec_r("a"); a.ld_abs_a(v1.DOOR_COUNT); a.jr("open_door6_advance", "nz")
    a.call("ray_map_cell"); a.cp_n(3); a.ret("nz")
    a.ld_a_abs(v1.RAY_XH); a.ld_r_r("b", "a")
    a.ld_a_abs(v1.RAY_YH); a.ld_r_r("c", "a"); a.call("lookup_door_bc")
    a.or_r("a"); a.ret("z")
    a.ld_a_abs(DOOR_ACTIVE_STATE); a.or_r("a"); a.ret("nz")
    a.ld_a_abs(DOOR_ACTIVE_FLAGS); a.and_n(DOOR_FLAG_LOCK_SENTINEL); a.jr("open_door6_unlocked", "z")
    a.ld_a_abs(EXIT_ACTIVE); a.or_r("a"); a.jr("open_door6_unlocked", "nz")
    a.call("sound_locked"); a.ret()
    a.label("open_door6_unlocked")
    a.ld_r_n("a", 1); a.ld_abs_a(DOOR_ACTIVE_STATE)
    a.xor_r("a"); a.ld_abs_a(DOOR_ACTIVE_FRACTION)
    a.call("store_active_door"); a.call("sound_door"); a.ret()
    a.label("open_door_legacy")
    a.ld_a_abs(ANGLE); a.call("ray_setup"); a.ld_r_n("a", 2); a.ld_abs_a(v1.DOOR_COUNT)
    a.label("open_door_legacy_advance"); a.call("ray_advance"); a.ld_a_abs(v1.DOOR_COUNT); a.dec_r("a"); a.ld_abs_a(v1.DOOR_COUNT); a.jr("open_door_legacy_advance", "nz")
    a.call("ray_map_cell"); a.cp_n(3); a.ret("nz"); a.xor_r("a"); a.ld_hl_a(); a.call("sound_door"); a.ret()


def emit_reprojection(a: Assembler) -> None:
    a.label("populate_reprojection_guards")
    if ENABLE_MICRO_REPROJECTION:
        for row in range(12):
            a.ld_a_abs(VIEW_MAP + row * 32); a.ld_abs_a(VIEW_MAP + row * 32 + 31)
            a.ld_a_abs(VIEW_MAP + row * 32 + 19); a.ld_abs_a(VIEW_MAP + row * 32 + 20)
    a.ret()

    a.label("update_reprojection_vblank")
    if ENABLE_MICRO_REPROJECTION:
        a.ld_a_abs(INPUT_LAST_RAW); a.and_n(0x02); a.jr("reproject_not_left", "z")
        a.ld_a_abs(REPROJECT_OFFSET); a.cp_n((-REPROJECT_LIMIT) & 0xFF); a.jr("reproject_store", "z"); a.dec_r("a"); a.jr("reproject_store")
        a.label("reproject_not_left"); a.ld_a_abs(INPUT_LAST_RAW); a.and_n(0x01); a.jr("reproject_decay", "z")
        a.ld_a_abs(REPROJECT_OFFSET); a.cp_n(REPROJECT_LIMIT); a.jr("reproject_store", "z"); a.inc_r("a"); a.jr("reproject_store")
        a.label("reproject_decay"); a.ld_a_abs(REPROJECT_OFFSET); a.or_r("a"); a.jr("reproject_store", "z"); a.cb("bit", "a", 7); a.jr("reproject_decay_negative", "nz"); a.dec_r("a"); a.jr("reproject_store")
        a.label("reproject_decay_negative"); a.inc_r("a")
        a.label("reproject_store"); a.ld_abs_a(REPROJECT_OFFSET); a.ldh_n_a(SCX)
        # Shift only published world OBJ X coordinates. The next frame's
        # shadow packet may be under construction and is never read here.
        # These sixteen byte stores happen wholly inside VBlank; UI objects
        # keep their positions. Base X is refreshed only on a real commit.
        a.ld_r_r("b", "a")
        for index in range(ENTITY_OAM_COUNT):
            a.ld_a_abs(PUBLISHED_WORLD_X + index); a.sub_r("b")
            a.ld_abs_a(0xFE00 + (ENTITY_OAM_FIRST + index) * 4 + 1)
    a.ret()

    a.label("reset_reprojection_for_commit")
    a.xor_r("a"); a.ld_abs_a(REPROJECT_OFFSET); a.ldh_n_a(SCX); a.ret()

    a.label("stat_isr")
    a.push("af")
    if HUD_UNSIGNED:
        a.ldh_a_n(LCDC); a.or_n(0x10); a.ldh_n_a(LCDC)
    a.xor_r("a"); a.ldh_n_a(SCX); a.pop("af"); a.reti()
