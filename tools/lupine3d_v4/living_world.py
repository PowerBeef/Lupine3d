"""SM83 emission for the v0.6 Living World gameplay slice."""
from __future__ import annotations

from sm83 import Assembler

from .layout import *  # noqa: F401,F403
from .resources import make_entity_tiles, make_oam_shadow  # noqa: F401


def emit_level_loader(a: Assembler) -> None:
    # LEVEL_INDEX selects the campaign level. Its bank and the page of its slot
    # in that bank are the only variables in the payload, which is laid out at
    # fixed offsets inside the slot (see levels.py); the resident directory
    # gives both, so the hot segment lookup only has to read two bytes.
    a.label("select_level")
    a.ld_a_abs(LEVEL_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "level_directory"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_abs_a(LEVEL_BANK); a.ld_a_hl(); a.ld_abs_a(LEVEL_PAGE); a.ret()

    a.label("load_level")
    a.call("invalidate_wall_cache")
    a.call("select_level")
    a.ld_a_abs(LEVEL_BANK); a.ld_abs_a(0x2000)
    a.ld_rr_nn("hl", LEVEL_GRID_OFFSET); add_level_page(a)
    a.ld_rr_nn("de", MAP); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    # The resident slice consumes a fixed header but the authored source owns
    # all coordinates, profiles, spawns, door metadata, and exit placement.
    a.ld_rr_nn("hl", LEVEL_HEADER_OFFSET); add_level_page(a)
    a.inc_rr("hl"); a.inc_rr("hl")  # width, height
    # The palette set is a fixed-WRAM campaign scalar: enter_world uploads
    # the set it names with the LCD off, after this loader has run.
    for address in (VRAM_PROFILE, PALETTE_SET):
        a.ldi_a_hl(); a.ld_abs_a(address)
    for address in (
        PLAYER_XL, PLAYER_XH, PLAYER_YL, PLAYER_YH, ANGLE,
        SENTINEL_XL, SENTINEL_XH, SENTINEL_YL, SENTINEL_YH,
        SENTINEL_HEALTH,
    ):
        a.ldi_a_hl(); a.ld_abs_a(address)
    # Authored in Q4 cells; the AI compares whole cells, as the attack test
    # does, so fold the fraction away once here rather than on every tick.
    a.ldi_a_hl(); a.cb("swap", "a"); a.and_n(0x0F); a.ld_abs_a(ACTIVATION_RADIUS)
    # Counts and the pickup value used to be assembled as immediate operands
    # from the single build-time level; a campaign has to read them per level.
    for address in (EXIT_CELL_X, EXIT_CELL_Y, DOOR_COUNT,
                    ACTOR_COUNT, LEVEL_FIXTURE_COUNT, LEVEL_PICKUP_VALUE):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_rr_nn("hl", LEVEL_DOOR_OFFSET); add_level_page(a); a.ld_rr_nn("de", DOOR_TABLE)
    a.ld_rr_nn("bc", MAX_DOORS * DOOR_RECORD_BYTES); a.call("copy_bc")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.ld_r_n("a", WORLD_MODE_LIVING); a.ld_abs_a(WORLD_MODE)
    a.xor_r("a"); a.ld_abs_a(PLAYER_KEYS)   # a card opens doors in its own sector
    a.ld_abs_a(SECTOR_KILLS)
    # Time is counted in VBlanks off the monotonic simulation clock, which is
    # in fixed WRAM and so readable under any bank.
    a.ld_a_abs(SIM_CLOCK); a.ld_abs_a(SECTOR_START)
    a.ld_a_abs(SIM_CLOCK + 1); a.ld_abs_a(SECTOR_START + 1)
    # The arsenal follows the sector (WEAPON_UNLOCK_SECTORS), so a continue
    # code restores it for free and one that moves backwards takes a weapon
    # away; a weapon in hand that is no longer owned drops to the first.
    a.ld_a_abs(LEVEL_INDEX); a.ld_r_n("b", 0b0011)
    for index in range(2, WEAPON_COUNT):
        a.cp_n(WEAPON_UNLOCK_SECTORS[index]); a.jr("weapons_owned_ready", "c"); a.ld_r_n("b", (2 << index) - 1)
    a.label("weapons_owned_ready"); a.ld_r_r("a", "b"); a.ld_abs_a(WEAPONS_OWNED)
    a.ld_a_abs(WEAPON_INDEX); a.and_n(WEAPON_COUNT - 1); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "weapon_bit_masks"); a.add_hl_rr("de"); a.ld_a_hl(); a.and_r("b"); a.jr("weapon_in_hand_owned", "nz")
    a.xor_r("a"); a.ld_abs_a(WEAPON_INDEX)
    a.label("weapon_in_hand_owned")
    # The first sector is the start of a run: a death retries a sector and
    # keeps the totals, a continue code starts them from where it drops you.
    a.ld_a_abs(LEVEL_INDEX); a.or_r("a"); a.jr("load_level_totals_kept", "nz")
    a.xor_r("a")
    for address in (CAMPAIGN_KILLS, CAMPAIGN_TIME, CAMPAIGN_TIME + 1):
        a.ld_abs_a(address)
    a.label("load_level_totals_kept")
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
    if SABLE_ART or COMPACT_DISPLAY: a.call("init_art_clocks")
    a.call("init_actors"); a.ret()


def emit_oam_system(a: Assembler) -> None:
    a.label("init_oam")
    a.ld_r_n("a", BOOT_ASSETS_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_rr_label("hl", "oam_initial"); a.ld_rr_nn("de", OAM_SHADOW); a.ld_rr_nn("bc", OAM_BYTES); a.call("copy_bc")
    a.ld_rr_label("hl", "oam_dma_stub"); a.ld_rr_nn("de", OAM_DMA_HRAM); a.ld_rr_nn("bc", OAM_DMA_STUB_BYTES); a.call("copy_bc")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT)
    for index in range(MAX_ACTORS + 1): a.ld_abs_a(LOD_HISTORY + index)
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
    for index in range(MAX_ACTORS): a.ld_abs_a(ACTOR_PROJECTED + index)
    a.ld_rr_nn("hl", WORLD_SCANLINES); a.ld_r_n("b", 144)
    a.label("clear_world_scanlines"); a.ldi_hl_a(); a.dec_r("b"); a.jr("clear_world_scanlines", "nz")
    if SCANLINE_ADMISSION or SABLE_ART: a.ld_abs_a(ADMISSION_MODE)
    if SCANLINE_ADMISSION: a.call("seed_foreground_scanlines")
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

    a.label("sound_swap")
    # A short mechanical clack: something heavy seating, not a reader beeping.
    a.xor_r("a"); a.ldh_n_a(NR10)
    a.ld_r_n("a", 0x40); a.ldh_n_a(NR11)
    a.ld_r_n("a", 0x91); a.ldh_n_a(NR12)
    a.ld_r_n("a", 0x60); a.ldh_n_a(NR13)
    a.ld_r_n("a", 0xC4); a.ldh_n_a(NR14)
    a.ret()

    a.label("sound_keycard")
    # Two short high blips: a reader refusing, not a bolt holding.
    a.xor_r("a"); a.ldh_n_a(NR10)
    a.ld_r_n("a", 0xC0); a.ldh_n_a(NR11)
    a.ld_r_n("a", 0x63); a.ldh_n_a(NR12)
    a.ld_r_n("a", 0xC0); a.ldh_n_a(NR13)
    a.ld_r_n("a", 0xC6); a.ldh_n_a(NR14)
    a.ret()

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
    if ACTOR_PRECISION: a.jp("project_entity_q8")
    a.label("project_entity_q4_reference")
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
    a.add_a_n(HORIZON); a.cp_n(VIEW_HEIGHT + 1); a.jr("entity_foot_in_view", "c"); a.ld_r_n("a", VIEW_HEIGHT)
    a.label("entity_foot_in_view"); a.add_a_n(16); a.ld_abs_a(ENTITY_FOOT_Y)
    a.ld_a_abs(DECAL_PROJECTING); a.or_r("a"); a.jr("entity_project_occlusion", "z")
    a.ld_r_n("a", 1); a.ld_abs_a(SENTINEL_VISIBLE); a.ret()
    a.label("entity_project_occlusion")
    if PHYSICAL_DEPTH:
        # Live aiming uses the fresh transform and its own LOS ray. It must
        # not consult render-depth ownership in the live-world bank.
        a.ldh_a_n(SVBK); a.and_n(7); a.cp_n(2); a.jr("entity_snapshot_occlusion","nz")
        a.ld_r_n("a",1); a.ld_abs_a(SENTINEL_VISIBLE); a.ret()
        a.label("entity_snapshot_occlusion")

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
    if PHYSICAL_DEPTH:
        a.ld_abs_a(PIXEL_INDEX); a.call("physical_bit_address")
        a.ld_rr_nn("hl",PIXEL_DEPTH_VALID); a.add_hl_rr("de"); a.ld_a_hl(); a.and_r("b")
        a.jr("entity_depth_valid","nz")
        a.ld_rr_nn("hl",PHYSICAL_DEPTH_MISSING); a.inc_r("(hl)"); a.jp("entity_strip_next")
        a.label("entity_depth_valid")
        a.ld_a_abs(ENTITY_TMP_L); a.ld_r_r("e","a"); a.ld_r_n("d",0)
        a.ld_rr_nn("hl",PIXEL_DEPTH); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b","a")
    else:
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
    # A dormant actor wakes when the player comes inside the level's authored
    # activation radius, rather than two AI ticks after the level loads.
    # sentinel_line_of_sight has just left the cell deltas in LOS_DX/LOS_DY.
    a.ld_a_abs(ACTIVATION_RADIUS); a.ld_r_r("b", "a")
    a.ld_a_abs(LOS_DX); a.cp_r("b"); a.ret("nc")
    a.ld_a_abs(LOS_DY); a.cp_r("b"); a.ret("nc")
    a.ld_r_n("a", SENTINEL_PATROL); a.ld_abs_a(SENTINEL_STATE)
    a.label("ai_not_dormant")
    a.ld_a_abs(LOS_RESULT); a.or_r("a"); a.jr("ai_patrol", "z")
    a.ld_a_abs(LOS_DX); a.cp_n(2); a.jr("ai_chase", "nc"); a.ld_a_abs(LOS_DY); a.cp_n(2); a.jr("ai_chase", "nc")
    a.ld_r_n("a", SENTINEL_ATTACK); a.ld_abs_a(SENTINEL_STATE)
    a.ld_a_abs(SENTINEL_COOLDOWN); a.or_r("a"); a.jr("ai_animate", "nz")
    if SABLE_ART:
        a.ld_r_n("a",1); a.call("stamp_actor_reaction"); a.call("stamp_player_hurt")
    a.call("sound_hurt")
    a.call("actor_kind_record")
    a.ldi_a_hl(); a.ld_r_r("b", "a")                     # authored contact damage
    a.ld_a_hl(); a.ld_abs_a(SENTINEL_COOLDOWN)           # this kind's recovery
    a.call("scale_contact_damage")
    a.ld_a_abs(PLAYER_HEALTH); a.sub_r("b"); a.jr("ai_health_store", "nc"); a.xor_r("a")
    a.label("ai_health_store"); a.ld_abs_a(PLAYER_HEALTH); a.jr("ai_animate")
    a.label("ai_chase"); a.ld_r_n("a", SENTINEL_CHASE); a.ld_abs_a(SENTINEL_STATE); a.call("sentinel_chase_step"); a.jr("ai_animate")
    a.label("ai_patrol"); a.ld_r_n("a", SENTINEL_PATROL); a.ld_abs_a(SENTINEL_STATE); a.call("sentinel_patrol_step")
    a.label("ai_animate")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_ATTACK); a.ld_r_n("a", 2); a.jr("ai_animation_store", "z")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_HURT); a.ld_r_n("a", 3); a.jr("ai_animation_store", "z")
    a.ld_a_abs(SENTINEL_AI_PHASE); a.and_n(1)
    a.label("ai_animation_store"); a.ld_abs_a(SENTINEL_ANIM); a.ret()

    a.label("actor_kind_record")   # HL -> the loaded actor's stat record
    a.ld_a_abs(SENTINEL_KIND); a.and_n(3)
    for _ in range(ACTOR_KIND_RECORD_BYTES.bit_length() - 1): a.add_a_r("a")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "actor_kind_stats"); a.add_hl_rr("de"); a.ret()

    a.label("actor_kind_drop")    # A = what this kind leaves when it dies
    a.call("actor_kind_record")
    a.ld_rr_nn("de", ACTOR_KIND_DROP); a.add_hl_rr("de"); a.ld_a_hl(); a.ret()

    a.label("actor_kind_step")    # ACTOR_STEP = this kind's Q8 move per AI tick
    a.call("actor_kind_record"); a.inc_rr("hl"); a.inc_rr("hl")
    a.ld_a_hl(); a.ld_abs_a(ACTOR_STEP); a.ret()

    a.label("scale_contact_damage")  # B = authored damage -> skill-scaled damage
    a.ld_a_abs(DIFFICULTY); a.or_r("a"); a.jr("damage_not_easy", "nz")
    a.ld_r_r("a", "b"); a.cb("srl", "a"); a.ld_r_r("b", "a"); a.ret()
    a.label("damage_not_easy"); a.cp_n(2); a.ret("c")
    a.ld_r_r("a", "b"); a.cb("srl", "a"); a.add_a_r("b"); a.ld_r_r("b", "a"); a.ret()

    a.label("actor_patrol_pointer")   # HL -> this actor's patrol heading
    a.ld_a_abs(ENTITY_SLOT); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", ACTOR_PATROL); a.add_hl_rr("de"); a.ret()

    a.label("sentinel_patrol_step")
    # A route rather than a bob. Each actor keeps a heading beside its slot -
    # the 16-byte slot itself is exactly full - and walks it at its kind's own
    # speed through the same stepping bodies and collision test the chase uses.
    # A refused step turns the actor a quarter turn, so it follows a wall
    # instead of grinding against it.
    a.call("actor_kind_step")
    a.call("actor_patrol_pointer"); a.push("hl")
    a.ld_a_hl(); a.and_n(3)
    a.jr("patrol_x_positive", "z")
    a.dec_r("a"); a.jr("patrol_x_negative", "z")
    a.dec_r("a"); a.jr("patrol_y_positive", "z")
    a.call("sentinel_step_y_negative"); a.jr("patrol_stepped")
    a.label("patrol_x_positive"); a.call("sentinel_step_x_positive"); a.jr("patrol_stepped")
    a.label("patrol_x_negative"); a.call("sentinel_step_x_negative"); a.jr("patrol_stepped")
    a.label("patrol_y_positive"); a.call("sentinel_step_y_positive")
    a.label("patrol_stepped")
    a.pop("hl"); a.ret("z")             # the step was taken; keep the heading
    a.ld_a_hl(); a.inc_r("a"); a.and_n(3); a.ld_hl_a(); a.ret()

    a.label("sentinel_chase_step")
    # Move along the dominant cell delta at this kind's speed. The Q8 step and
    # boundary map test keep the actor inside empty cells without a general
    # physics system.
    a.call("actor_kind_step")
    a.ld_a_abs(LOS_DX); a.ld_r_r("b", "a"); a.ld_a_abs(LOS_DY); a.cp_r("b"); a.jr("sentinel_chase_y", "nc")
    a.ld_a_abs(LOS_SX); a.cp_n(1); a.jr("sentinel_step_x_negative", "nz")
    # The four stepping bodies are named because patrol calls them directly.
    # Each returns Z when the step was taken and NZ when the shared collision
    # test refused it.
    a.label("sentinel_step_x_positive")
    a.ld_a_abs(ACTOR_STEP); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_XL); a.add_a_r("b"); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_XH); a.adc_a_n(0); a.ld_abs_a(v1.CAND_H); a.jr("sentinel_chase_x_test")
    a.label("sentinel_step_x_negative")
    a.ld_a_abs(ACTOR_STEP); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_XL); a.sub_r("b"); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_XH); a.sbc_a_n(0); a.ld_abs_a(v1.CAND_H)
    a.label("sentinel_chase_x_test")
    for source, dest in ((v1.CAND_L, COLLISION_X), (v1.CAND_H, COLLISION_X + 1), (SENTINEL_YL, COLLISION_Y), (SENTINEL_YH, COLLISION_Y + 1)):
        a.ld_a_abs(source); a.ld_abs_a(dest)
    a.ld_a_abs(v1.CAND_H); a.ld_r_r("b", "a"); a.ld_a_abs(SENTINEL_YH); a.ld_r_r("c", "a"); a.call("collision_cell_bc"); a.or_r("a"); a.ret("nz")
    a.ld_a_abs(v1.CAND_L); a.ld_abs_a(SENTINEL_XL); a.ld_a_abs(v1.CAND_H); a.ld_abs_a(SENTINEL_XH); a.ret()
    a.label("sentinel_chase_y")
    a.ld_a_abs(LOS_SY); a.cp_n(1); a.jp("sentinel_step_y_negative", "nz")
    a.label("sentinel_step_y_positive")
    a.ld_a_abs(ACTOR_STEP); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_YL); a.add_a_r("b"); a.ld_abs_a(v1.CAND_L)
    a.ld_a_abs(SENTINEL_YH); a.adc_a_n(0); a.ld_abs_a(v1.CAND_H); a.jr("sentinel_chase_y_test")
    a.label("sentinel_step_y_negative")
    a.ld_a_abs(ACTOR_STEP); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_YL); a.sub_r("b"); a.ld_abs_a(v1.CAND_L)
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
    a.call("sound_pickup")
    # A drop does not carry a kind byte of its own: it is whatever the actor
    # that left it was, which is already in the slot and already snapshotted.
    a.call("actor_kind_drop"); a.cp_n(DROP_KIND_IDS["keycard"]); a.jr("pickup_keycard", "z")
    a.ld_a_abs(LEVEL_PICKUP_VALUE); a.ld_r_r("b", "a")
    a.ld_a_abs(PLAYER_HEALTH); a.add_a_r("b"); a.jr("pickup_health_store", "nc"); a.ld_r_n("a", 0xFF)
    a.label("pickup_health_store"); a.ld_abs_a(PLAYER_HEALTH); a.jr("check_level_exit")
    a.label("pickup_keycard"); a.ld_r_n("a", 1); a.ld_abs_a(PLAYER_KEYS)
    a.label("check_level_exit")
    a.ld_a_abs(EXIT_ACTIVE); a.or_r("a"); a.ret("z")
    a.ld_a_abs(PLAYER_XH); a.ld_r_r("b", "a"); a.ld_a_abs(EXIT_CELL_X); a.cp_r("b"); a.ret("nz")
    a.ld_a_abs(PLAYER_YH); a.ld_r_r("b", "a"); a.ld_a_abs(EXIT_CELL_Y); a.cp_r("b"); a.ret("nz")
    # The player stands on the exit cell for several ticks before the mode
    # changes, so only the first one counts: otherwise the sector is folded
    # into the run once per tick, and the sting retriggers with it.
    a.ld_a_abs(LEVEL_COMPLETE); a.or_r("a"); a.ret("nz")
    a.ld_r_n("a", 1); a.ld_abs_a(LEVEL_COMPLETE)
    a.call("stamp_sector_result"); a.jp("sound_complete")

    a.label("stamp_sector_result")
    # SECTOR_TIME = SIM_CLOCK - SECTOR_START, then fold the sector into the run.
    a.ld_a_abs(SIM_CLOCK); a.ld_r_r("b", "a")
    a.ld_a_abs(SECTOR_START); a.ld_r_r("c", "a")
    a.ld_r_r("a", "b"); a.sub_r("c"); a.ld_abs_a(SECTOR_TIME)
    a.ld_a_abs(SIM_CLOCK + 1); a.ld_r_r("b", "a")
    a.ld_a_abs(SECTOR_START + 1); a.ld_r_r("c", "a")
    a.ld_r_r("a", "b"); a.sbc_a_r("c"); a.ld_abs_a(SECTOR_TIME + 1)
    a.ld_a_abs(CAMPAIGN_TIME); a.ld_r_r("b", "a")
    a.ld_a_abs(SECTOR_TIME); a.add_a_r("b"); a.ld_abs_a(CAMPAIGN_TIME)
    a.ld_a_abs(CAMPAIGN_TIME + 1); a.ld_r_r("b", "a")
    a.ld_a_abs(SECTOR_TIME + 1); a.adc_a_r("b"); a.ld_abs_a(CAMPAIGN_TIME + 1)
    a.ld_a_abs(CAMPAIGN_KILLS); a.ld_r_r("b", "a")
    a.ld_a_abs(SECTOR_KILLS); a.add_a_r("b"); a.ld_abs_a(CAMPAIGN_KILLS); a.ret()

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
    # The occluder test has slack: an actor's centre sits on the wall plane it
    # is pressed against, and Q5 rounding can put it a unit past it, while an
    # actor that really is behind a wall or a closed panel is at least half a
    # cell further. Without the slack a chaser hugging a wall could not be hit.
    a.ld_a_abs(DEPTH_RESULT); a.add_a_n(HITSCAN_DEPTH_SLACK); a.jr("hit_depth_ready", "nc"); a.ld_r_n("a", 255)
    a.label("hit_depth_ready"); a.ld_r_r("b", "a")
    a.ld_a_abs(SENTINEL_DEPTH); a.cp_r("b"); a.ret("nc")
    if SABLE_ART:
        a.ld_r_n("a",2); a.call("stamp_actor_reaction")
    # What a hit takes off is the weapon's, not the engine's.
    a.call("weapon_damage"); a.ld_r_r("c", "a")
    a.ld_a_abs(SENTINEL_HEALTH); a.sub_r("c"); a.jr("hit_health_floor", "nc"); a.xor_r("a")
    a.label("hit_health_floor")
    a.ld_abs_a(SENTINEL_HEALTH); a.jr("sentinel_survived_hit", "nz")
    if SABLE_ART:
        a.ld_r_n("a",3); a.call("stamp_actor_reaction")
    a.ld_r_n("a", SENTINEL_DEAD); a.ld_abs_a(SENTINEL_STATE)
    a.ld_a_abs(SECTOR_KILLS); a.inc_r("a"); a.ld_abs_a(SECTOR_KILLS)
    a.ld_r_n("a", 1); a.ld_abs_a(PICKUP_ACTIVE); a.ld_abs_a(EXIT_ACTIVE)
    a.jp("sound_kill")
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
    a.ld_a_abs(DOOR_ACTIVE_FLAGS); a.and_n(DOOR_FLAG_KEYCARD); a.jr("open_door6_sentinel_lock", "z")
    a.ld_a_abs(PLAYER_KEYS); a.or_r("a"); a.jr("open_door6_refused", "z")
    a.label("open_door6_sentinel_lock")
    a.ld_a_abs(DOOR_ACTIVE_FLAGS); a.and_n(DOOR_FLAG_LOCK_SENTINEL); a.jr("open_door6_unlocked", "z")
    a.ld_a_abs(EXIT_ACTIVE); a.or_r("a"); a.jr("open_door6_unlocked", "nz")
    # Two refusals, told apart by the flag that marks the way out: the exit
    # says the outpost is not clear, anything else says it wants a card.
    a.label("open_door6_refused")
    a.ld_a_abs(DOOR_ACTIVE_FLAGS); a.and_n(DOOR_FLAG_EXIT); a.jp("sound_locked", "nz")
    a.jp("sound_keycard")
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
    a.xor_r("a"); a.ldh_n_a(SCX)
    # The raster switch is done. The music sequencer ticks here rather than in
    # VBlank: a staged publication has about one scanline of margin before
    # line 153, and this boundary is forty lines away from it.
    a.push("bc"); a.push("hl"); a.call("music_tick"); a.pop("hl"); a.pop("bc")
    a.pop("af"); a.reti()
