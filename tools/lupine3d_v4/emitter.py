"""SM83 routine emission for the v0.4 rendering kernel."""
from __future__ import annotations

from sm83 import Assembler

from .layout import *  # noqa: F401,F403
from .resources import *  # noqa: F401,F403

def emit_mul_u8(a: Assembler) -> None:
    """B*C -> HL through a four-bank exact MBC5 product table.

    DDA components are bounded to 0..127, so C selects one of 128 complete
    256-entry product rows.  This replaces an eight-iteration shift/add loop
    without changing a single arithmetic result.
    """
    a.label("mul_u8")
    a.ld_r_r("a", "c")
    # C >> 5: rotating the top three bits down and masking costs 20 cycles,
    # versus 40 for five CB-prefixed shifts. The exact table is unchanged.
    for _ in range(3): a.rlca()
    a.and_n(7)
    a.add_a_n(PRODUCT_LUT_BASE_BANK); a.ld_abs_a(0x2000)
    # Address = $4000 + (C&31)*512 + B*2.
    a.ld_r_r("a", "c"); a.and_n(0x1F); a.add_a_r("a"); a.ld_r_r("d", "a")
    a.ld_r_r("a", "b"); a.add_a_r("a"); a.ld_r_r("l", "a")
    a.ld_r_n("a", 0); a.adc_a_n(0); a.or_r("d"); a.or_n(0x40); a.ld_r_r("h", "a")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
    a.ret()


def emit_div_u16_u8_sat(a: Assembler) -> None:
    """HL/B -> A, saturated to 255. B must be nonzero for normal division."""
    a.label("div_u16_u8_sat")
    a.ld_r_r("a", "b"); a.or_r("a"); a.jr("div_sat", "z")
    a.ld_r_r("a", "h"); a.cp_r("b"); a.jr("div_sat", "nc")
    a.ld_r_r("a", "h"); a.ld_r_r("c", "l")
    a.ld_r_n("d", 0); a.ld_r_n("e", 8)
    a.label("div_loop")
    a.cb("sla", "c"); a.rla(); a.cb("sla", "d")
    a.cp_r("b"); a.jr("div_no_sub", "c")
    a.sub_r("b"); a.inc_r("d")
    a.label("div_no_sub")
    a.dec_r("e"); a.jr("div_loop", "nz")
    a.ld_r_r("a", "d"); a.ret()
    a.label("div_sat")
    a.ld_r_n("a", 0xFF); a.ret()


def emit_div_u16_u8_sat9(a: Assembler) -> None:
    """HL/B -> 9-bit quotient as PROJECTION_PAGE:A, saturated to 511."""
    a.label("div_u16_u8_sat9")
    a.xor_r("a"); a.ld_abs_a(PROJECTION_PAGE)
    a.ld_r_r("a", "b"); a.or_r("a"); a.jr("div9_sat", "z")
    # A quotient below 256 can use the compact existing divider directly.
    a.ld_r_r("a", "h"); a.cp_r("b"); a.jp("div_u16_u8_sat", "c")
    # Subtract B*256.  The residual quotient is the low byte and the table
    # page records the implicit +256.  A second full page saturates to 511.
    a.sub_r("b"); a.ld_r_r("h", "a"); a.cp_r("b"); a.jr("div9_sat", "nc")
    a.ld_r_n("a", 1); a.ld_abs_a(PROJECTION_PAGE)
    a.jp("div_u16_u8_sat")
    a.label("div9_sat")
    a.ld_r_n("a", 1); a.ld_abs_a(PROJECTION_PAGE)
    a.ld_r_n("a", 0xFF); a.ret()


def emit_palette_init(a: Assembler) -> None:
    """Upload all eight BG palettes and the two OBJ palettes in use."""
    a.label("init_palettes")
    a.ld_r_n("a", 0x80); a.ldh_n_a(BGPI)
    a.ld_rr_label("hl", "bg_palettes"); a.ld_r_n("b", 64)
    a.label("init_bg_palette_loop")
    a.ldi_a_hl(); a.ldh_n_a(BGPD); a.dec_r("b"); a.jr("init_bg_palette_loop", "nz")
    a.ld_r_n("a", 0x80); a.ldh_n_a(OBPI)
    a.ld_rr_label("hl", "obj_palettes"); a.ld_r_n("b", 64)
    a.label("init_obj_palette_loop")
    a.ldi_a_hl(); a.ldh_n_a(OBPD); a.dec_r("b"); a.jr("init_obj_palette_loop", "nz")
    a.ret()


def emit_hud_system(a: Assembler) -> None:
    """Large health/remaining-hostile digits and a literal exit-status label."""
    from .artwork import hud_assets
    a.label("prepare_hud_tiles")
    for item, name in enumerate(("health", "hostiles")):
        if name == "health":
            a.ld_a_abs(PLAYER_HEALTH); a.cp_n(100); a.jr("hud_health_ready", "c")
            a.ld_r_n("a", 99); a.label("hud_health_ready")
        else:
            a.ld_r_n("b", 0)
            for index in range(MAX_ACTORS):
                a.ld_a_abs(ACTOR_COUNT); a.cp_n(index + 1); a.jr(f"hud_actor_{index}_skip", "c")
                a.ld_a_abs(ENTITY_SLOTS + index * 16 + 4); a.cp_n(SENTINEL_DEAD); a.jr(f"hud_actor_{index}_skip", "z")
                a.inc_r("b"); a.label(f"hud_actor_{index}_skip")
            a.ld_r_r("a", "b")
        a.ld_r_n("b", 0); a.label(f"hud_{name}_divide")
        a.cp_n(10); a.jr(f"hud_{name}_digits", "c")
        a.sub_n(10); a.inc_r("b"); a.jr(f"hud_{name}_divide")
        a.label(f"hud_{name}_digits"); a.add_a_r("a"); a.add_a_n(HUD_DIGIT_BASE); a.ld_r_r("c", "a")
        a.ld_r_r("a", "b"); a.add_a_r("a"); a.add_a_n(HUD_DIGIT_BASE); a.ld_r_r("b", "a")
        for row in (0,1):
            a.ld_rr_nn("hl", HUD_PACKET + item*4 + row*2)
            a.ld_r_r("a", "b")
            if row: a.inc_r("a")
            a.ldi_hl_a(); a.ld_r_r("a", "c")
            if row: a.inc_r("a")
            a.ld_hl_a()
    a.ld_a_abs(EXIT_ACTIVE); a.and_n(1); a.ld_r_r("b", "a")
    a.ld_a_abs(PLAYER_HEALTH); a.or_r("a"); a.jr("hud_status_alive", "nz"); a.ld_r_n("b", 2)
    a.label("hud_status_alive"); a.ld_a_abs(LEVEL_COMPLETE); a.or_r("a"); a.jr("hud_status_ready", "z"); a.ld_r_n("b", 3)
    a.label("hud_status_ready")
    a.ld_r_r("a", "b"); a.add_a_r("a"); a.add_a_r("b"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "hud_status_records"); a.add_hl_rr("de")
    for i in range(3):
        a.ldi_a_hl(); a.ld_abs_a(HUD_PACKET + 8 + i)
    a.ret()
    a.label("update_hud_tiles")
    a.ld_rr_nn("hl", HUD_PACKET)
    a.xor_r("a"); a.ldh_n_a(VBK)
    for item, column in enumerate((HUD_HEALTH_TENS_X, HUD_STATUS_TENS_X)):
        for row in (0,1):
            for digit in (0,1):
                a.ldi_a_hl()
                for base in (0x9800, 0x9C00):
                    a.ld_abs_a(base + (HUD_ROW+row)*32 + column + digit)
    for i in range(3):
        a.ldi_a_hl()
        for base in (0x9800, 0x9C00): a.ld_abs_a(base+17*32+16+i)
    a.ret()
def emit_vram_init(a: Assembler) -> None:
    def copy_atlas(length: int) -> None:
        # Signed IDs wrap physically at 128: never stream across $9800 maps.
        first = min(length, (128 - ATLAS_TILE_BASE) * 16)
        a.ld_rr_nn("de", bg_tile_address(ATLAS_TILE_BASE)); a.ld_rr_nn("bc", first); a.call("copy_bc")
        if length > first:
            a.ld_rr_nn("de", 0x8800); a.ld_rr_nn("bc", length - first); a.call("copy_bc")

    a.label("upload_profile_tiles")
    a.ld_a_abs(VRAM_PROFILE); a.cp_n(ACTIVE_LEVEL.vram_profile); a.jr("upload_active_profile_tiles", "z")
    a.ld_r_n("a", BANKED_ATLAS_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_rr_nn("hl", BANKED_ATLAS_TILES_ADDRESS); copy_atlas(len(BANKED_ATLAS_TILES))
    a.ld_r_n("a", BOOT_ASSETS_ROM_BANK); a.ld_abs_a(0x2000); a.jr("upload_profile_entity_art")
    a.label("upload_active_profile_tiles")
    a.ld_rr_label("hl", "active_atlas_tiles"); copy_atlas(len(ACTIVE_ATLAS_TILES))
    a.label("upload_profile_entity_art")
    # Source cels stay in ROM; only admitted masked pairs occupy OBJ VRAM.
    a.ret()

    a.label("init_vram")
    a.call("invalidate_wall_cache")
    a.ld_r_n("a", BOOT_ASSETS_ROM_BANK); a.ld_abs_a(0x2000)
    # The map upload covers all 32 bytes of each of the twelve viewport rows.
    # Initialize the hidden padding once instead of relying on WRAM power-on
    # contents that happen to be zero in the project harness.
    a.ld_rr_nn("hl", VIEW_MAP); a.ld_rr_nn("bc", 12 * 32); a.ld_r_n("d", CEILING_TILE)
    a.label("init_view_map_loop")
    a.ld_r_r("a", "d"); a.ldi_hl_a(); a.dec_rr("bc")
    a.ld_r_r("a", "b"); a.or_r("c"); a.jr("init_view_map_loop", "nz")
    # Bank 0: shared static viewport tiles, UI tiles and tile maps.
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "static_view_tiles"); a.ld_rr_nn("de", bg_tile_address(CEILING_TILE)); a.ld_rr_nn("bc", STATIC_VIEW_TILES * 16); a.call("copy_bc")
    a.call("upload_profile_tiles")
    a.ld_rr_label("hl", "ui_tiles"); a.ld_rr_nn("de", 0x8F00); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    from .artwork import hud_assets
    a.ld_rr_label("hl", "hud_tiles"); a.ld_rr_nn("de", 0x8200); a.ld_rr_nn("bc", len(hud_assets()[0])); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    # Bank 1 mirrors viewport tiles and holds weapon OBJ tiles plus attributes.
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "static_view_tiles"); a.ld_rr_nn("de", bg_tile_address(CEILING_TILE)); a.ld_rr_nn("bc", STATIC_VIEW_TILES * 16); a.call("copy_bc")
    a.call("upload_profile_tiles")
    a.ld_rr_label("hl", "weapon_tiles"); a.ld_rr_nn("de", 0x8000 + WEAPON_TILE_BASE * 16); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_rr_label("hl", "obj_ui_tiles"); a.ld_rr_nn("de", 0x8500); a.ld_rr_nn("bc", 64); a.call("copy_bc")
    a.ld_rr_label("hl", "attrmap_page0"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "attrmap_page1"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()


def emit_dma(a: Assembler) -> None:
    a.label("upload_dynamic_tiles")
    a.ld_a_abs(DYN_COUNT); a.or_r("a"); a.ret("z")
    a.ld_r_r("b", "a")
    a.ld_r_n("a", 0xC0); a.ldh_n_a(HDMA1)
    a.xor_r("a"); a.ldh_n_a(HDMA2); a.ldh_n_a(HDMA4)
    a.ld_r_n("a", (DYNAMIC_TILE_VRAM >> 8) & 0x1F); a.ldh_n_a(HDMA3)
    a.ld_r_r("a", "b"); a.dec_r("a"); a.ldh_n_a(HDMA5)
    a.ret()
    a.label("upload_view_map")
    # Tile IDs always live in VRAM bank 0; bank 1 holds CGB attributes.
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_r_n("a", 0xC6); a.ldh_n_a(HDMA1)
    a.xor_r("a"); a.ldh_n_a(HDMA2)
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.or_r("a"); a.jr("upload_map_9800", "z")
    a.ld_r_n("a", 0x1C); a.jr("upload_map_dest_ready")
    a.label("upload_map_9800")
    a.ld_r_n("a", 0x18)
    a.label("upload_map_dest_ready")
    a.ldh_n_a(HDMA3); a.xor_r("a"); a.ldh_n_a(HDMA4)
    a.ld_r_n("a", 0x17); a.ldh_n_a(HDMA5)  # 24 blocks = 384 bytes
    a.ret()

    a.label("upload_initial_both_pages")
    # Dynamic tile pixels live in the VRAM bank selected by each page's
    # preloaded attribute map. Tile-number maps themselves always live in
    # VRAM bank 0; writing them with VBK=1 would corrupt CGB attributes.
    a.xor_r("a"); a.ldh_n_a(VBK); a.call("upload_dynamic_tiles")
    a.ld_r_n("a", 1); a.ld_abs_a(CURRENT_PAGE)  # hidden page = 0 -> 9800
    a.xor_r("a"); a.ldh_n_a(VBK); a.call("upload_view_map")
    a.ld_r_n("a", 1); a.ldh_n_a(VBK); a.call("upload_dynamic_tiles")
    a.xor_r("a"); a.ld_abs_a(CURRENT_PAGE)     # hidden page = 1 -> 9C00
    a.ldh_n_a(VBK); a.call("upload_view_map")
    # Build both initial attribute packets using the same page rule as normal
    # publication. LCD is off, so no staging or partial-packet exposure.
    a.ld_r_n("a", 1); a.ld_abs_a(CURRENT_PAGE); a.call("build_surface_attributes"); a.call("upload_surface_attributes")
    a.xor_r("a"); a.ld_abs_a(CURRENT_PAGE); a.call("build_surface_attributes"); a.call("upload_surface_attributes")
    a.call("upload_masked_tiles"); a.call("publish_oam_packet")
    a.ld_a_abs(OBJ_PAGE); a.xor_n(1); a.ld_abs_a(OBJ_PAGE)
    a.ld_r_n("a", 1); a.ld_abs_a(CURRENT_PAGE); a.call("build_surface_attributes")
    a.xor_r("a"); a.ld_abs_a(CURRENT_PAGE); a.ldh_n_a(VBK); a.ret()

    a.label("upload_hidden_page")
    a.xor_r("a"); a.ld_abs_a(FRAME_REUSED)
    a.call("prepare_hud_tiles")
    a.call("build_surface_attributes")
    a.call("wait_vblank")
    # Upload dynamic pixels to the hidden page's selected tile-data bank.
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ldh_n_a(VBK)
    a.call("upload_dynamic_tiles")
    # Stage large packets in hidden memory, retaining the old complete BG/OAM
    # epoch. Publish map, HUD and OAM together in the following VBlank.
    # Reserve the HUD/OAM tail and avoid the CGB's early LY=0 on line 153.
    a.ld_a_abs(MASK_TILE_COUNT); a.ld_r_r("b", "a"); a.ld_a_abs(DYN_COUNT); a.add_a_r("b"); a.cp_n(25); a.jr("upload_packet_ready", "c")
    a.call("wait_vblank")
    a.label("upload_packet_ready")
    a.call("upload_masked_tiles")
    if ENABLE_MICRO_REPROJECTION:
        # The optional published-X copy needs extra headroom with a full OBJ
        # packet. Keep all visible state on the old epoch until the last wait.
        a.ld_a_abs(MASK_TILE_COUNT); a.cp_n(25); a.jr("reprojection_packet_fits", "c")
        a.call("wait_vblank"); a.label("reprojection_packet_fits")
    a.call("upload_surface_attributes")
    # Upload tile numbers after the matching hidden bank-1 attributes.
    a.xor_r("a"); a.ldh_n_a(VBK); a.call("upload_view_map")
    a.call("update_hud_tiles")
    a.call("update_muzzle_oam"); a.call("publish_oam_packet")
    if ENABLE_MICRO_REPROJECTION:
        a.call("reset_reprojection_for_commit")
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ld_abs_a(CURRENT_PAGE)
    a.or_r("a"); a.jr("display_page_zero", "z")
    a.ld_r_n("a", BG_LCDC | 8); a.ldh_n_a(LCDC); a.jr("display_page_done")
    a.label("display_page_zero")
    a.ld_r_n("a", BG_LCDC); a.ldh_n_a(LCDC)
    a.label("display_page_done")
    a.ld_r_n("a", 1); a.ld_abs_a(WALL_CACHE_VALID)
    a.jp("finish_presentation")


def emit_input_system(a: Assembler) -> None:
    """Emit VBlank sampling, timestamped packet production and legacy polling.

    The ISR does not simulate. Cooperative render yields consume packets in
    the isolated live-world bank, leaving the render snapshot unchanged.
    """
    a.label("sample_joypad_latched")
    a.ld_r_n("a", 0x20); a.ldh_n_a(P1)
    a.ldh_a_n(P1); a.ldh_a_n(P1)
    a.cpl(); a.and_n(0x0F); a.ld_r_r("b", "a")
    a.ld_r_n("a", 0x10); a.ldh_n_a(P1)
    a.ldh_a_n(P1); a.ldh_a_n(P1)
    a.cpl(); a.and_n(0x0F); a.cb("swap", "a"); a.or_r("b"); a.ld_r_r("c", "a")
    # Rising edges = raw & ~last_raw. Preserve every edge until main consumes it.
    a.ld_a_abs(INPUT_LAST_RAW); a.cpl(); a.and_r("c"); a.ld_r_r("b", "a")
    a.ld_a_abs(INPUT_EDGE_LATCH); a.or_r("b"); a.ld_abs_a(INPUT_EDGE_LATCH)
    a.ld_r_r("a", "c"); a.ld_abs_a(INPUT_LAST_RAW); a.ld_abs_a(BUTTONS)
    a.ld_r_n("a", 0x30); a.ldh_n_a(P1)
    a.ret()

    a.label("vblank_isr")
    # The sampler uses only AF/BC. A minimal save set keeps the once-per-VBlank
    # latency tax small while retaining instruction-boundary transparency.
    a.push("af"); a.push("bc"); a.push("hl"); a.call("sample_joypad_latched")
    if HUD_UNSIGNED:
        a.ldh_a_n(LCDC); a.and_n(0xEF); a.ldh_n_a(LCDC)
    # This is a VBlank clock, not a count of arbitrary joypad polls.
    a.ld_a_abs(INPUT_SAMPLE_COUNT); a.inc_r("a"); a.ld_abs_a(INPUT_SAMPLE_COUNT)
    if FIXED_SIMULATION:
        a.call("queue_vblank_input")
    if ENABLE_MICRO_REPROJECTION:
        a.call("update_reprojection_vblank")
    a.pop("hl"); a.pop("bc"); a.pop("af"); a.reti()

    a.label("update_input")
    # Main-loop polling preserves the old immediate action semantics. DI also
    # makes the sampler/latch pair non-reentrant when a VBlank lands here.
    a.di(); a.call("sample_joypad_latched")
    a.ld_a_abs(INPUT_EDGE_LATCH); a.ld_abs_a(PRESSED)
    a.xor_r("a"); a.ld_abs_a(INPUT_EDGE_LATCH)
    a.ld_a_abs(BUTTONS); a.ld_abs_a(PREV_BUTTONS)
    a.ei()
    a.label("apply_input_actions")
    # Turn and move from one stable held-state snapshot.
    a.ld_a_abs(PREV_BUTTONS); a.and_n(0x02); a.jr("no_turn_left", "z")
    a.ld_a_abs(ANGLE); a.sub_n(1 if FIXED_SIMULATION else 4); a.ld_abs_a(ANGLE)
    a.label("no_turn_left")
    a.ld_a_abs(PREV_BUTTONS); a.and_n(0x01); a.jr("no_turn_right", "z")
    a.ld_a_abs(ANGLE); a.add_a_n(1 if FIXED_SIMULATION else 4); a.ld_abs_a(ANGLE)
    a.label("no_turn_right")
    a.ld_a_abs(PREV_BUTTONS); a.and_n(0x04); a.jr("no_move_forward", "z")
    a.ld_a_abs(ANGLE); a.call("move_player")
    a.label("no_move_forward")
    a.ld_a_abs(PREV_BUTTONS); a.and_n(0x08); a.jr("no_move_backward", "z")
    a.ld_a_abs(ANGLE); a.add_a_n(128); a.call("move_player")
    a.label("no_move_backward")
    a.ld_a_abs(PRESSED); a.and_n(0x20); a.jr("no_open_door", "z"); a.call("open_door")
    a.label("no_open_door")
    a.ld_a_abs(PRESSED); a.and_n(0x10); a.jr("no_shoot", "z")
    a.ld_r_n("a", 9 if FIXED_SIMULATION else 3); a.ld_abs_a(FLASH); a.call("sound_shoot"); a.call("player_fire_hitscan")
    a.label("no_shoot")
    a.ret()

    a.label("update_muzzle_oam")
    a.ld_a_abs(FLASH); a.or_r("a"); a.jr("muzzle_hidden", "z")
    a.dec_r("a"); a.ld_abs_a(FLASH); a.ld_r_n("b", 56 + 16); a.jr("muzzle_shadow_compare")
    a.label("muzzle_hidden"); a.ld_r_n("b", 0)
    a.label("muzzle_shadow_compare")
    a.ld_a_abs(OAM_SHADOW + 9 * 4); a.cp_r("b"); a.ret("z")
    a.ld_r_r("a", "b"); a.ld_abs_a(OAM_SHADOW + 9 * 4)
    a.ld_r_n("a", 1); a.ld_abs_a(OAM_DIRTY); a.ret()


def emit_dda(a: Assembler) -> None:
    a.label("prepare_frame_boundaries")
    # Distance from the player fraction to each side of its current cell. The
    # four values are pose-invariant across every ray in one visual update.
    a.ld_a_abs(PLAYER_XL); a.ld_abs_a(FRAME_X_NEG_L); a.xor_r("a"); a.ld_abs_a(FRAME_X_NEG_H)
    a.ld_a_abs(PLAYER_XL); a.cpl(); a.inc_r("a"); a.ld_abs_a(FRAME_X_POS_L)
    a.ld_r_n("a", 0); a.jr("frame_x_pos_high_ready", "nz"); a.inc_r("a")
    a.label("frame_x_pos_high_ready"); a.ld_abs_a(FRAME_X_POS_H)
    a.ld_a_abs(PLAYER_YL); a.ld_abs_a(FRAME_Y_NEG_L); a.xor_r("a"); a.ld_abs_a(FRAME_Y_NEG_H)
    a.ld_a_abs(PLAYER_YL); a.cpl(); a.inc_r("a"); a.ld_abs_a(FRAME_Y_POS_L)
    a.ld_r_n("a", 0); a.jr("frame_y_pos_high_ready", "nz"); a.inc_r("a")
    a.label("frame_y_pos_high_ready"); a.ld_abs_a(FRAME_Y_POS_H); a.ret()

    a.label("dda_setup")
    # Map coordinates.
    a.ld_a_abs(PLAYER_XH); a.ld_abs_a(DDA_MAP_X)
    a.ld_a_abs(PLAYER_YH); a.ld_abs_a(DDA_MAP_Y)

    # One sequential four-byte fetch replaces two tables plus sign decoding.
    load_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.add_hl_rr("hl"); a.add_hl_rr("hl")
    a.ld_rr_label("de", "ray_vectors_packed"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_abs_a(DDA_ABS_X)
    a.ldi_a_hl(); a.ld_abs_a(DDA_ABS_Y)
    a.ldi_a_hl(); a.ld_abs_a(DDA_STEP_X)
    a.ld_a_hl(); a.ld_abs_a(DDA_STEP_Y)

    # Initial distance to next X boundary in Q8.8.
    a.ld_a_abs(DDA_STEP_X); a.cp_n(1); a.jr("dda_next_x_positive", "z")
    a.cp_n(0xFF); a.jr("dda_next_x_negative", "z")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_NEXT_X_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_positive")
    a.ld_a_abs(FRAME_X_POS_L); a.ld_abs_a(DDA_NEXT_X_L); a.ld_a_abs(FRAME_X_POS_H); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_negative")
    a.ld_a_abs(FRAME_X_NEG_L); a.ld_abs_a(DDA_NEXT_X_L); a.ld_a_abs(FRAME_X_NEG_H); a.ld_abs_a(DDA_NEXT_X_H)
    a.label("dda_next_x_done")

    # Initial distance to next Y boundary.
    a.ld_a_abs(DDA_STEP_Y); a.cp_n(1); a.jr("dda_next_y_positive", "z")
    a.cp_n(0xFF); a.jr("dda_next_y_negative", "z")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_positive")
    a.ld_a_abs(FRAME_Y_POS_L); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_a_abs(FRAME_Y_POS_H); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_negative")
    a.ld_a_abs(FRAME_Y_NEG_L); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_a_abs(FRAME_Y_NEG_H); a.ld_abs_a(DDA_NEXT_Y_H)
    a.label("dda_next_y_done")

    # Special axial rays avoid product overflow/sentinel arithmetic.
    a.ld_a_abs(DDA_ABS_X); a.or_r("a"); a.jr("dda_error_x_nonzero", "nz")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_ERR_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_ERR_H); a.jr("dda_error_done")
    a.label("dda_error_x_nonzero")
    a.ld_a_abs(DDA_ABS_Y); a.or_r("a"); a.jr("dda_error_general", "nz")
    a.xor_r("a"); a.ld_abs_a(DDA_ERR_L); a.ld_r_n("a", 0x80); a.ld_abs_a(DDA_ERR_H); a.jr("dda_error_done")

    a.label("dda_error_general")
    # X product = nextX * absY.
    a.ld_a_abs(DDA_NEXT_X_L); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_ABS_Y); a.ld_r_r("c", "a"); a.call("mul_u8")
    a.ld_a_abs(DDA_NEXT_X_H); a.or_r("a"); a.jr("dda_xprod_no_high", "z")
    a.ld_a_abs(DDA_ABS_Y); a.add_a_r("h"); a.ld_r_r("h", "a")
    a.label("dda_xprod_no_high")
    a.ld_r_r("a", "l"); a.ld_abs_a(DDA_ERR_L); a.ld_r_r("a", "h"); a.ld_abs_a(DDA_ERR_H)
    # Y product, then error = X - Y.
    a.ld_a_abs(DDA_NEXT_Y_L); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_ABS_X); a.ld_r_r("c", "a"); a.call("mul_u8")
    a.ld_a_abs(DDA_NEXT_Y_H); a.or_r("a"); a.jr("dda_yprod_no_high", "z")
    a.ld_a_abs(DDA_ABS_X); a.add_a_r("h"); a.ld_r_r("h", "a")
    a.label("dda_yprod_no_high")
    a.ld_a_abs(DDA_ERR_L); a.sub_r("l"); a.ld_abs_a(DDA_ERR_L)
    a.ld_a_abs(DDA_ERR_H); a.sbc_a_r("h"); a.ld_abs_a(DDA_ERR_H)
    a.label("dda_error_done")
    a.xor_r("a"); a.ld_abs_a(DDA_CROSSINGS); a.ret()

    a.label("dda_read_cell")
    a.ld_a_abs(DDA_MAP_Y); a.cb("swap", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_MAP_X); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0)
    a.ld_a_hl(); a.ret()

    a.label("dda_cast")
    a.xor_r("a"); a.ld_abs_a(Q14_ACTIVE); a.ld_abs_a(Q14_LOADED)
    a.call("dda_setup")
    a.ld_a_abs(Q14_RECORD); a.cp_n(255); a.jr("dda_loop", "z")
    a.call("dda_read_cell"); a.cp_n(3); a.jp("q14_restart", "z")
    a.label("dda_loop")
    if Q14_ORDER_ENABLED:
        a.call("q14_crossing_uncertain"); a.jp("q14_resume", "nz")
    # Choose X on negative or zero signed error; Y on positive error.
    a.ld_a_abs(DDA_ABS_X); a.or_r("a"); a.jp("dda_step_y", "z")
    a.ld_a_abs(DDA_ABS_Y); a.or_r("a"); a.jp("dda_step_x", "z")
    a.ld_a_abs(DDA_ERR_H); a.cb("bit", "a", 7); a.jp("dda_step_x", "nz")
    a.or_r("a"); a.jp("dda_step_y", "nz")
    a.ld_a_abs(DDA_ERR_L); a.or_r("a"); a.jp("dda_step_y", "nz")

    a.label("dda_step_x")
    a.ld_a_abs(DDA_STEP_X); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_MAP_X); a.add_a_r("b"); a.ld_abs_a(DDA_MAP_X)
    a.xor_r("a"); a.ld_abs_a(DDA_AXIS)
    a.ld_a_abs(DDA_NEXT_X_L); a.ld_abs_a(DDA_DIST_L); a.ld_a_abs(DDA_NEXT_X_H); a.ld_abs_a(DDA_DIST_H)
    a.call("dda_post_step"); a.ret("nz")
    a.ld_a_abs(DDA_NEXT_X_H); a.inc_r("a"); a.ld_abs_a(DDA_NEXT_X_H)
    a.ld_a_abs(DDA_ABS_Y); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_ERR_H); a.add_a_r("b"); a.ld_abs_a(DDA_ERR_H)
    a.jp("dda_loop")

    a.label("dda_step_y")
    a.ld_a_abs(DDA_STEP_Y); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_MAP_Y); a.add_a_r("b"); a.ld_abs_a(DDA_MAP_Y)
    a.ld_r_n("a", 1); a.ld_abs_a(DDA_AXIS)
    a.ld_a_abs(DDA_NEXT_Y_L); a.ld_abs_a(DDA_DIST_L); a.ld_a_abs(DDA_NEXT_Y_H); a.ld_abs_a(DDA_DIST_H)
    a.call("dda_post_step"); a.ret("nz")
    a.ld_a_abs(DDA_NEXT_Y_H); a.inc_r("a"); a.ld_abs_a(DDA_NEXT_Y_H)
    a.ld_a_abs(DDA_ABS_X); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_ERR_H); a.sub_r("b"); a.ld_abs_a(DDA_ERR_H)
    a.jp("dda_loop")

    a.label("dda_post_step")
    a.ld_a_abs(DDA_CROSSINGS); a.inc_r("a"); a.ld_abs_a(DDA_CROSSINGS); a.cp_n(32); a.jr("dda_force_hit", "nc")
    a.call("dda_read_cell"); a.cp_n(3); a.jr("dda_regular_cell", "nz")
    a.call("door_ray_hit")
    a.label("dda_regular_cell"); a.or_r("a"); a.jr("dda_hit", "nz")
    a.xor_r("a"); a.ret()
    a.label("dda_force_hit")
    a.ld_r_n("a", 1)
    a.label("dda_hit")
    a.ld_abs_a(DDA_MATERIAL); a.or_r("a"); a.ret()


def emit_projection_and_casting(a: Assembler) -> None:
    a.label("project_hit")
    # Q5 distance: D32 = round(axis distance / 8), saturated to 511.
    # The additional fractional bit materially reduces near-wall height
    # quantization while keeping the product inside 16 bits.
    a.ld_a_abs(DDA_DIST_L); a.add_a_n(4); a.ld_r_r("l", "a")
    a.ld_a_abs(DDA_DIST_H); a.adc_a_n(0); a.ld_r_r("h", "a")
    for _ in range(3):
        a.cb("srl", "h"); a.cb("rr", "l")
    a.ld_r_r("a", "h"); a.cp_n(2); a.jr("project_d32_sat", "nc")
    a.ld_abs_a(D32_HIGH); a.ld_r_r("b", "l"); a.jr("project_d32_ready")
    a.label("project_d32_sat")
    a.ld_r_n("a", 1); a.ld_abs_a(D32_HIGH); a.ld_r_n("b", 0xFF)
    a.label("project_d32_ready")
    a.ld_r_r("a", "b"); a.ld_abs_a(D32_LOW)
    # Select the component perpendicular to the wall exactly as the former
    # arithmetic path did. The table's paired 1024-byte slices are ordered by
    # component*18 + (correction-110).
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("project_component_y", "nz")
    a.ld_a_abs(DDA_ABS_X); a.jr("project_component_ready")
    a.label("project_component_y"); a.ld_a_abs(DDA_ABS_Y)
    a.label("project_component_ready")
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.ld_r_r("d", "h"); a.ld_r_r("e", "l")
    for _ in range(4): a.add_hl_rr("hl")
    a.add_hl_rr("de"); a.add_hl_rr("de")
    a.ld_a_abs(DDA_CORRECTION); a.sub_n(PROJECTION_LUT_CORRECTION_MIN); a.ld_abs_a(LUT_CORRECTION)
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.add_hl_rr("de")
    a.ld_r_r("a", "l"); a.ld_abs_a(LUT_SLICE_LOW)
    # Bank = 2 + slice/16. The selected bank is restored to bank 1 before
    # any conventional engine data in $4000-$7FFF is touched again.
    for _ in range(4): a.cb("srl", "h"); a.cb("rr", "l")
    a.ld_r_r("a", "l"); a.add_a_n(PROJECTION_LUT_BASE_BANK); a.ld_abs_a(0x2000)
    # Address = $4000 + (slice&15)*1024 + D32*2.
    a.ld_a_abs(LUT_SLICE_LOW); a.and_n(0x0F); a.add_a_r("a"); a.add_a_r("a"); a.or_n(0x40); a.ld_r_r("h", "a")
    a.ld_a_abs(D32_LOW); a.add_a_r("a"); a.ld_r_r("l", "a")
    a.ld_a_abs(D32_HIGH); a.adc_a_r("a"); a.or_r("h"); a.ld_r_r("h", "a")
    a.ldi_a_hl(); a.ld_abs_a(TOP_RESULT); a.ld_a_hl(); a.ld_abs_a(DEPTH_RESULT)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)

    # Exact wall-side style.
    a.ld_a_abs(DDA_MATERIAL); a.cp_n(3); a.jr("style_door", "z"); a.cp_n(2); a.jr("style_tech", "z")
    a.ld_a_abs(DDA_AXIS); a.jr("style_store")
    a.label("style_tech"); a.ld_a_abs(DDA_AXIS); a.add_a_n(2); a.jr("style_store")
    a.label("style_door"); a.ld_r_n("a", 4)
    a.label("style_store"); a.ld_abs_a(STYLE_RESULT)

    # Compact face identity: axis | material | wall-plane coordinate.
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("face_axis_y", "nz")
    a.ld_a_abs(DDA_MAP_X); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_STEP_X); a.cp_n(0xFF); a.jr("face_x_plane_ready", "nz"); a.inc_r("b")
    a.label("face_x_plane_ready"); a.ld_a_abs(DDA_MAP_Y); a.ld_abs_a(ALONG_RESULT); a.xor_r("a"); a.ld_r_r("d", "a"); a.jr("face_pack")
    a.label("face_axis_y")
    a.ld_a_abs(DDA_MAP_Y); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_STEP_Y); a.cp_n(0xFF); a.jr("face_y_plane_ready", "nz"); a.inc_r("b")
    a.label("face_y_plane_ready"); a.ld_a_abs(DDA_MAP_X); a.ld_abs_a(ALONG_RESULT); a.ld_r_n("d", 0x80)
    a.label("face_pack")
    a.ld_a_abs(DDA_MATERIAL); a.and_n(3)
    for _ in range(5): a.add_a_r("a")
    a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.and_n(0x1F); a.or_r("c"); a.or_r("d"); a.ld_abs_a(FACE_RESULT)
    a.call("lookup_segment_id"); a.ret()

    a.label("lookup_segment_id")
    # Side order matches the build-time table: west, east, north, south.
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("segment_axis_y", "nz")
    a.ld_a_abs(DDA_STEP_X); a.cp_n(0xFF); a.ld_r_n("a", 0); a.jr("segment_side_ready", "nz")
    a.inc_r("a"); a.jr("segment_side_ready")
    a.label("segment_axis_y")
    a.ld_a_abs(DDA_STEP_Y); a.cp_n(0xFF); a.ld_r_n("a", 2); a.jr("segment_side_ready", "nz"); a.inc_r("a")
    a.label("segment_side_ready")
    a.ld_r_r("c", "a")
    a.ld_a_abs(DDA_MAP_Y); a.cb("swap", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_MAP_X); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    a.add_hl_rr("hl"); a.add_hl_rr("hl")
    a.ld_r_r("e", "c"); a.ld_r_n("d", 0); a.add_hl_rr("de")
    a.ld_rr_nn("de", SEGMENT_TABLE_ROM_ADDRESS); a.add_hl_rr("de")
    a.ld_r_n("a", SEGMENT_TABLE_ROM_BANK); a.ld_abs_a(0x2000); a.ld_a_hl(); a.ld_abs_a(SEGMENT_RESULT)
    a.ld_rr_nn("de", 1024); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(SURFACE_RESULT)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ret()

    a.label("cast_one_v2"); a.call("dda_cast")
    a.label("cast_precision_done"); a.call("project_hit")
    a.ld_r_n("a", 255); a.ld_abs_a(Q14_RECORD); a.ret()

    a.label("cast_indexed")  # Public self-contained probe entry.
    a.call("prepare_frame_boundaries"); a.jp("cast_indexed_prepared")
    a.label("cast_indexed_prepared")  # CAST_INDEX selects the ray
    a.ld_a_abs(CAST_INDEX); a.ld_abs_a(Q14_RECORD)
    a.ld_a_abs(CAST_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "ray_offsets_q10"); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(ANGLE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(RAY_PLAYER_SHIFT): a.add_hl_rr("hl")
    a.add_hl_rr("de")
    a.ld_r_r("a", "h"); a.and_n(RAY_DIRECTION_HIGH_MASK); a.ld_r_r("h", "a"); store_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_a_abs(CAST_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "ray_corrections"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(DDA_CORRECTION)
    a.call("cast_one_v2"); a.ret()

    a.label("cast_physical_indexed")  # Public self-contained probe entry.
    a.call("prepare_frame_boundaries"); a.jp("cast_physical_indexed_prepared")
    a.label("cast_physical_indexed_prepared")  # PIXEL_INDEX selects one of 160 columns
    a.ld_a_abs(PIXEL_INDEX); a.add_a_n(80); a.ld_abs_a(Q14_RECORD)
    a.ld_a_abs(PIXEL_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("a", 0); a.adc_a_n(0); a.ld_r_r("d", "a")
    a.ld_rr_label("hl", "physical_offsets_q10"); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(ANGLE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(RAY_PLAYER_SHIFT): a.add_hl_rr("hl")
    a.add_hl_rr("de")
    a.ld_r_r("a", "h"); a.and_n(RAY_DIRECTION_HIGH_MASK); a.ld_r_r("h", "a"); store_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_a_abs(PIXEL_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "physical_corrections"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(DDA_CORRECTION)
    a.call("cast_one_v2"); a.ret()

    a.label("cast_and_store")  # input A ray index
    a.ld_abs_a(CAST_INDEX)
    a.ld_a_abs(ADAPTIVE_CASTS); a.inc_r("a"); a.ld_abs_a(ADAPTIVE_CASTS)
    a.call("cast_indexed_prepared")
    a.ld_a_abs(CAST_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_abs(TOP_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_abs(STYLE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_abs(FACE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_abs(ALONG_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_DEPTH); a.add_hl_rr("de"); a.ld_a_abs(DEPTH_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_SEGMENT); a.add_hl_rr("de"); a.ld_a_abs(SEGMENT_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_SURFACE); a.add_hl_rr("de"); a.ld_a_abs(SURFACE_RESULT); a.ld_hl_a(); a.ret()

    a.label("cast_physical_and_store")
    a.ld_a_abs(EDGE_RECASTS); a.inc_r("a"); a.ld_abs_a(EDGE_RECASTS)
    a.call("cast_physical_indexed_prepared")
    a.ld_a_abs(PIXEL_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    for address, result in (
        (PIXEL_TOPS, TOP_RESULT), (PIXEL_STYLES, STYLE_RESULT),
        (PIXEL_KEYS, FACE_RESULT), (PIXEL_ALONG, ALONG_RESULT),
        (PIXEL_SEGMENT, SEGMENT_RESULT),
        (PIXEL_SURFACE, SURFACE_RESULT),
    ):
        a.ld_rr_nn("hl", address); a.add_hl_rr("de"); a.ld_a_abs(result); a.ld_hl_a()
    a.ret()

    a.label("cast_all")
    a.xor_r("a"); a.ld_abs_a(Q14_FALLBACKS)
    a.call("prepare_frame_boundaries")
    a.xor_r("a"); a.ld_abs_a(ADAPTIVE_CASTS); a.call("cast_and_store")
    a.ld_r_n("a", 2); a.ld_abs_a(ADAPTIVE_INDEX)
    a.label("cast_anchor_loop")
    if FIXED_SIMULATION:
        a.call("render_yield")
    a.ld_a_abs(ADAPTIVE_INDEX); a.call("cast_and_store")
    a.ld_a_abs(ADAPTIVE_INDEX); a.add_a_n(2); a.ld_abs_a(ADAPTIVE_INDEX); a.cp_n(80); a.jr("cast_anchor_loop", "c")
    a.ld_r_n("a", 79); a.call("cast_and_store")
    a.ld_r_n("a", 1); a.ld_abs_a(ADAPTIVE_INDEX)
    a.label("adaptive_fill_loop")
    if FIXED_SIMULATION:
        a.call("render_yield")
    # Compare left/right face keys.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jp("adaptive_cast_mid", "nz")
    # Identical packed planes are not enough: disconnected exposed runs can
    # share the same plane/material key. Segment IDs certify continuity.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_SEGMENT); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_SEGMENT); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jp("adaptive_cast_mid", "nz")
    # Same plane/material: require identical or adjacent along-plane cells.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_SURFACE); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_SURFACE); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jp("adaptive_cast_mid", "nz")
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.sub_r("b"); a.jr("adaptive_along_positive", "nc"); a.cpl(); a.inc_r("a")
    a.label("adaptive_along_positive"); a.cp_n(2); a.jp("adaptive_cast_mid", "nc")
    # Quantized projection is only approximately affine.  Require the two
    # anchors to differ by no more than two top-edge pixels; this preserves
    # the inexpensive midpoint path while eliminating large near-wall errors.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.sub_r("b"); a.jr("adaptive_top_positive", "nc"); a.cpl(); a.inc_r("a")
    a.label("adaptive_top_positive"); a.cp_n(3); a.jp("adaptive_cast_mid", "nc")
    # Affine midpoint of the two integer top edges.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.add_a_r("b"); a.inc_r("a"); a.cb("srl", "a"); a.ld_abs_a(TOP_RESULT)
    # Copy left style/key/along to midpoint.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(STYLE_RESULT)
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(FACE_RESULT)
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ALONG_RESULT)
    a.ld_rr_nn("hl", RAY_SEGMENT); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(SEGMENT_RESULT)
    a.ld_rr_nn("hl", RAY_SURFACE); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(SURFACE_RESULT)
    # Re-certify the interpolated top through the same conservative exact
    # projection class used by cast rays. Averaging depths can otherwise move
    # an occluder farther away than the nearer member of its top class.
    a.ld_a_abs(TOP_RESULT); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "top_depth_lut"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(DEPTH_RESULT)
    # Store the interpolated descriptor without incrementing cast count.
    a.ld_a_abs(ADAPTIVE_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_abs(TOP_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_abs(STYLE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_abs(FACE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_abs(ALONG_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_DEPTH); a.add_hl_rr("de"); a.ld_a_abs(DEPTH_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_SEGMENT); a.add_hl_rr("de"); a.ld_a_abs(SEGMENT_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_SURFACE); a.add_hl_rr("de"); a.ld_a_abs(SURFACE_RESULT); a.ld_hl_a(); a.jr("adaptive_fill_done")
    a.label("adaptive_cast_mid"); a.ld_a_abs(ADAPTIVE_INDEX); a.call("cast_and_store")
    a.label("adaptive_fill_done")
    a.ld_a_abs(ADAPTIVE_INDEX); a.add_a_n(2); a.ld_abs_a(ADAPTIVE_INDEX); a.cp_n(79); a.jp("adaptive_fill_loop", "c")
    a.call("build_pixel_descriptors"); a.call("decorate_pixel_styles"); a.ret()

    a.label("build_pixel_descriptors")
    a.xor_r("a"); a.ld_abs_a(PAIR_INDEX); a.ld_abs_a(EDGE_RECASTS)
    a.label("pixel_pair_loop")
    # Current pair-centre top.
    a.ld_a_abs(PAIR_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(TEMP_TOP)
    # Left physical top = round((3*current + previous) / 4).
    a.ld_a_abs(PAIR_INDEX); a.or_r("a"); a.jr("pixel_left_has_previous", "nz")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("b", "a"); a.jr("pixel_left_previous_ready")
    a.label("pixel_left_has_previous")
    a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.label("pixel_left_previous_ready")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("c", "a"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r("b"); a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(PAIR_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ld_hl_a()
    # Right physical top = round((3*current + following) / 4).
    a.ld_a_abs(PAIR_INDEX); a.cp_n(RAYS - 1); a.jr("pixel_right_has_following", "nz")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("b", "a"); a.jr("pixel_right_following_ready")
    a.label("pixel_right_has_following")
    a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.label("pixel_right_following_ready")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("c", "a"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r("b"); a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(PAIR_INDEX); a.add_a_r("a"); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ld_hl_a()
    # Geometry style, key and along-cell identity are initially duplicated.
    for source, destination in (
        (RAY_STYLES, PIXEL_STYLES), (RAY_KEYS, PIXEL_KEYS),
        (RAY_ALONG, PIXEL_ALONG), (RAY_SEGMENT, PIXEL_SEGMENT),
        (RAY_SURFACE, PIXEL_SURFACE),
    ):
        a.ld_a_abs(PAIR_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", source); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
        a.ld_a_abs(PAIR_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", destination); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ldi_hl_a(); a.ld_hl_a()
    a.ld_a_abs(PAIR_INDEX); a.inc_r("a"); a.ld_abs_a(PAIR_INDEX); a.cp_n(RAYS); a.jp("pixel_pair_loop", "c")

    # Recast only the two physical pixels adjacent to a pair-level face break.
    a.xor_r("a"); a.ld_abs_a(EDGE_INDEX)
    a.label("edge_recast_loop")
    a.ld_a_abs(EDGE_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("b", "a"); a.ld_a_hl(); a.cp_r("b"); a.jr("edge_recast_compare_segment", "z")
    a.jr("edge_recast_required")
    a.label("edge_recast_compare_segment")
    a.ld_a_abs(EDGE_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_SEGMENT); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("b", "a"); a.ld_a_hl(); a.cp_r("b"); a.jr("edge_recast_skip", "z")
    a.label("edge_recast_required")
    a.ld_a_abs(EDGE_INDEX); a.add_a_r("a"); a.inc_r("a"); a.ld_abs_a(PIXEL_INDEX); a.call("cast_physical_and_store")
    a.ld_a_abs(EDGE_INDEX); a.add_a_r("a"); a.add_a_n(2); a.ld_abs_a(PIXEL_INDEX); a.call("cast_physical_and_store")
    a.label("edge_recast_skip")
    a.ld_a_abs(EDGE_INDEX); a.inc_r("a"); a.ld_abs_a(EDGE_INDEX); a.cp_n(RAYS - 1); a.jp("edge_recast_loop", "c"); a.ret()

    a.label("decorate_pixel_styles")
    a.xor_r("a"); a.ld_abs_a(EVENT_COUNT); a.ld_r_n("a", 1); a.ld_abs_a(EVENT_INDEX)
    a.label("event_boundary_loop")
    # Physical segment identity is the geometry certificate. Material bits in
    # the face key are presentation only and may not create hard corners.
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_SEGMENT); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(EVENT_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", PIXEL_SEGMENT); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jr("event_same_segment", "z")
    # A true physical break receives one dark pixel when >=16 px tall.
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); a.jr("event_physical_lod_skip", "nc")
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", CREASE_STYLE); a.ld_hl_a()
    a.label("event_physical_lod_skip")
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT); a.jr("event_boundary_done")
    a.label("event_same_segment")
    # A material transition on one continuous plane is a soft seam. Count it
    # for diagnostics, but do not overwrite either physical pixel's style.
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(EVENT_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jr("event_same_material", "z")
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT); a.jr("event_boundary_done")
    a.label("event_same_material")
    # Cell boundaries remain classified for future sparse fasteners, but the
    # clarity pass deliberately emits no full-height technology rib.
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(EVENT_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", PIXEL_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jr("event_boundary_done", "z")
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT)
    a.label("event_boundary_done")
    a.ld_a_abs(EVENT_INDEX); a.inc_r("a"); a.ld_abs_a(EVENT_INDEX); a.cp_n(PHYSICAL_COLUMNS); a.jp("event_boundary_loop", "c")

    # Derive door frames and a run-centred spine from contiguous material-3
    # pixels. This is independent of screen-tile phase.
    a.xor_r("a"); a.ld_abs_a(EVENT_INDEX)
    a.label("door_scan_loop")
    a.ld_a_abs(EVENT_INDEX); a.cp_n(PHYSICAL_COLUMNS); a.ret("nc")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.and_n(0x60); a.cp_n(0x60); a.jp("door_scan_advance", "nz")
    a.ld_a_abs(EVENT_INDEX); a.ld_abs_a(DOOR_RUN_START)
    a.label("door_find_end")
    a.ld_a_abs(EVENT_INDEX); a.inc_r("a"); a.ld_abs_a(EVENT_INDEX); a.cp_n(PHYSICAL_COLUMNS); a.jr("door_end_ready", "nc")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.and_n(0x60); a.cp_n(0x60); a.jr("door_find_end", "z")
    a.label("door_end_ready")
    a.ld_a_abs(EVENT_INDEX); a.ld_abs_a(DOOR_RUN_END)
    # Frame at run start.
    a.ld_a_abs(DOOR_RUN_START); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); a.jr("door_start_lod_done", "nc"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", CREASE_STYLE); a.ld_hl_a()
    a.label("door_start_lod_done")
    # Frame at inclusive run end.
    a.ld_a_abs(DOOR_RUN_END); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); a.jr("door_end_lod_done", "nc"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", CREASE_STYLE); a.ld_hl_a()
    a.label("door_end_lod_done")
    # Require a three-pixel run before adding its centre spine.
    a.ld_a_abs(DOOR_RUN_END); a.ld_r_r("b", "a"); a.ld_a_abs(DOOR_RUN_START); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.sub_r("c"); a.cp_n(3); a.jr("door_event_count", "c")
    a.dec_r("a"); a.cb("srl", "a"); a.add_a_r("c"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(33); a.jr("door_event_count", "nc")
    a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", DOOR_SPINE_STYLE); a.ldi_hl_a(); a.ld_hl_a()
    a.label("door_event_count"); a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT); a.jp("door_scan_loop")
    a.label("door_scan_advance"); a.ld_a_abs(EVENT_INDEX); a.inc_r("a"); a.ld_abs_a(EVENT_INDEX); a.jp("door_scan_loop")

def emit_renderer(a: Assembler) -> None:
    # These two fixed-size kernels sit in the hottest compositor path.  The
    # looped versions spent roughly one quarter of their time decrementing a
    # counter and branching.  Unrolling costs well under 200 ROM bytes and
    # removes about one thousand cycles from every generated boundary tile.
    a.label("copy_16")  # HL source, DE destination
    for _ in range(16):
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()

    a.label("or_16")  # positioned HL source, DE destination
    for _ in range(16):
        a.ldi_a_hl(); a.ld_r_r("c", "a"); a.ld_a_mem_rr("de")
        a.or_r("c"); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()

    a.label("apply_surface_detail")
    # Spatial Clarity compiles this as a no-op. The dormant branch is retained
    # only to keep experimental renderer-profile builds reproducible.
    if SURFACE_DETAIL_ENABLED:
        a.ld_a_abs(TILE_Y0); a.cp_n(SURFACE_RAIL_Y0); a.ret("nz")
        a.ld_a_abs(DETAIL_MASK); a.cp_n(2); a.ret("nz"); a.ld_r_n("b", 0xFF)
        load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H)
        a.ld_a_hl(); a.or_r("b"); a.ld_hl_a()
        a.inc_rr("hl"); a.inc_rr("hl")
        a.ld_r_r("a", "b"); a.cpl(); a.ld_r_r("b", "a")
        a.ld_a_hl(); a.and_r("b"); a.ld_hl_a(); a.ret()
    else:
        a.ret()

    a.label("compute_strip_state")  # input A top, output A state
    a.ld_r_r("b", "a")
    a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.cp_r("b"); a.jr("strip_ceiling", "c")
    a.ld_r_n("a", 96); a.sub_r("b"); a.ld_r_r("c", "a")  # C = bottom
    a.ld_a_abs(TILE_Y0); a.cp_r("c"); a.jr("strip_floor", "nc")
    a.cp_r("b"); a.jr("strip_top_edge", "c")
    a.add_a_n(7); a.cp_r("c"); a.jr("strip_wall", "c")
    # Bottom edge: state = 10 + (bottom - y0), range 11..17.
    a.ld_r_r("a", "c"); a.ld_r_r("d", "a"); a.ld_a_abs(TILE_Y0); a.ld_r_r("e", "a"); a.ld_r_r("a", "d"); a.sub_r("e"); a.add_a_n(10); a.ret()
    a.label("strip_top_edge")
    a.ld_r_r("a", "b"); a.ld_r_r("d", "a"); a.ld_a_abs(TILE_Y0); a.ld_r_r("e", "a"); a.ld_r_r("a", "d"); a.sub_r("e"); a.add_a_n(3); a.ret()
    a.label("strip_ceiling"); a.xor_r("a"); a.ret()
    a.label("strip_floor"); a.ld_r_n("a", 1); a.ret()
    a.label("strip_wall"); a.ld_r_n("a", 2); a.ret()

    a.label("get_microstrip_ptr")
    # Base pointer for the style.
    a.ld_a_abs(STRIP_STYLE); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "microstrip_style_bases"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    # state * 128 + physical pixel * 16.
    a.ld_a_abs(STRIP_STATE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(7): a.add_hl_rr("hl")
    a.ld_a_abs(STRIP_PAIR); a.cb("swap", "a"); a.and_n(0xF0); a.ld_r_r("c", "a"); a.ld_r_n("b", 0); a.add_hl_rr("bc")
    a.add_hl_rr("de"); a.ret()

    a.label("get_pair_microstrip_ptr")
    a.ld_a_abs(STRIP_STYLE); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "pair_microstrip_style_bases"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    # state * 64 + pair * 16.
    a.ld_a_abs(STRIP_STATE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(6): a.add_hl_rr("hl")
    a.ld_a_abs(STRIP_PAIR); a.cb("srl", "a"); a.cb("swap", "a"); a.and_n(0xF0); a.ld_r_r("c", "a"); a.ld_r_n("b", 0); a.add_hl_rr("bc")
    a.add_hl_rr("de"); a.ret()

    a.label("build_tile_signature")
    # Hash y0, the already-produced dark mask, and the eight source tops in
    # place.  The earlier prototype copied all ten bytes into WRAM and then
    # read them back; direct hashing removes that entire memory pass.
    a.ld_r_n("c", 0)
    for address in (TILE_Y0, DARK_MASK):
        a.ld_r_r("a", "c"); a.rlca(); a.ld_r_r("c", "a")
        a.ld_a_abs(address); a.xor_r("c"); a.ld_r_r("c", "a")
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_r_n("b", 8)
    a.label("signature_hash_loop")
    a.ld_r_r("a", "c"); a.rlca(); a.ld_r_r("c", "a"); a.ldi_a_hl(); a.xor_r("c"); a.ld_r_r("c", "a")
    a.dec_r("b"); a.jr("signature_hash_loop", "nz")
    a.ld_r_r("a", "c"); a.ld_abs_a(SIGNATURE_HASH); a.ret()

    a.label("find_atlas_tile")
    a.ld_a_abs(SIGNATURE_HASH); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_a_abs(VRAM_PROFILE); a.cp_n(ACTIVE_LEVEL.vram_profile); a.jr("atlas_active_start", "z")
    a.ld_r_n("a", BANKED_ATLAS_ROM_BANK); a.ld_abs_a(0x2000); a.ld_rr_nn("hl", BANKED_ATLAS_BUCKET_START_ADDRESS); a.jr("atlas_start_ready")
    a.label("atlas_active_start"); a.ld_rr_label("hl", "active_atlas_bucket_start")
    a.label("atlas_start_ready"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(VRAM_PROFILE); a.cp_n(ACTIVE_LEVEL.vram_profile); a.jr("atlas_active_count", "z")
    a.ld_rr_nn("hl", BANKED_ATLAS_BUCKET_COUNT_ADDRESS); a.jr("atlas_count_ready")
    a.label("atlas_active_count"); a.ld_rr_label("hl", "active_atlas_bucket_count")
    a.label("atlas_count_ready"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ATLAS_ENTRY_COUNT); a.or_r("a"); a.jr("atlas_miss", "z")
    # HL = tile_atlas_entries + start * 11.
    a.ld_r_r("e", "b"); a.ld_r_n("d", 0); a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
    for _ in range(3): a.add_hl_rr("hl")
    for _ in range(3): a.add_hl_rr("de")
    a.ld_a_abs(VRAM_PROFILE); a.cp_n(ACTIVE_LEVEL.vram_profile); a.jr("atlas_active_entries", "z")
    a.ld_rr_nn("de", BANKED_ATLAS_ENTRIES_ADDRESS); a.jr("atlas_entries_ready")
    a.label("atlas_active_entries"); a.ld_rr_label("de", "active_atlas_entries")
    a.label("atlas_entries_ready"); a.add_hl_rr("de")
    store_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H)
    a.label("atlas_candidate_loop")
    load_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H)
    # Reject on the two cheapest fields before touching the eight-column
    # source array.  Exact top comparison keeps hash collisions harmless.
    a.ld_a_abs(TILE_Y0); a.cp_r("(hl)"); a.jr("atlas_candidate_mismatch", "nz"); a.inc_rr("hl")
    a.ld_a_abs(DARK_MASK); a.cp_r("(hl)"); a.jr("atlas_candidate_mismatch", "nz"); a.inc_rr("hl")
    a.push("hl"); load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.ld_r_n("b", 8)
    a.label("atlas_compare_loop")
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.cp_r("(hl)"); a.jr("atlas_candidate_mismatch", "nz")
    a.inc_rr("hl"); a.dec_r("b"); a.jr("atlas_compare_loop", "nz")
    a.ld_a_hl(); a.jr("atlas_return")
    a.label("atlas_candidate_mismatch")
    load_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H); a.ld_rr_nn("de", TILE_ATLAS_ENTRY_BYTES); a.add_hl_rr("de"); store_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H)
    a.ld_a_abs(ATLAS_ENTRY_COUNT); a.dec_r("a"); a.ld_abs_a(ATLAS_ENTRY_COUNT); a.jr("atlas_candidate_loop", "nz")
    a.label("atlas_miss"); a.xor_r("a")
    a.label("atlas_return")
    # The inactive profile metadata lives in a high MBC5 bank; all
    # conventional engine data expects bank 1 on return.
    a.ld_r_r("b", "a"); a.ld_a_abs(VRAM_PROFILE); a.cp_n(ACTIVE_LEVEL.vram_profile); a.ld_r_r("a", "b"); a.ret("z")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ld_r_r("a", "b"); a.ret()

    a.label("compose_dynamic_tile")
    load_hl_abs(a, DYN_PTR_L, DYN_PTR_H); store_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H)
    a.xor_r("a"); a.ld_abs_a(STRIP_PAIR)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.push("hl")
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.label("compose_pair_loop")
    a.ldi_a_hl(); a.ld_abs_a(TEMP_TOP)
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.and_n(1); a.ld_abs_a(STRIP_STYLE)
    a.xor_r("a"); a.ld_abs_a(STRIP_KIND)
    # Keep the original two-pixel fast path whenever both synthesized pixels
    # have the same silhouette and visual light/dark style.
    a.ld_a_abs(STRIP_PAIR); a.and_n(1); a.jr("compose_strip_ready", "nz")
    a.ld_a_hl(); a.ld_abs_a(SECOND_TOP); a.ld_r_r("b", "a"); a.ld_a_abs(TEMP_TOP); a.cp_r("b"); a.jr("compose_strip_ready", "nz")
    a.ld_a_mem_rr("de"); a.and_n(1); a.ld_abs_a(SECOND_STYLE); a.ld_r_r("b", "a"); a.ld_a_abs(STRIP_STYLE); a.cp_r("b"); a.jr("compose_strip_ready", "nz")
    a.inc_rr("hl"); a.inc_rr("de"); a.ld_r_n("a", 1); a.ld_abs_a(STRIP_KIND)
    a.label("compose_strip_ready")
    a.push("hl"); a.push("de")
    a.ld_a_abs(TEMP_TOP); a.call("compute_strip_state"); a.ld_abs_a(STRIP_STATE)
    a.ld_a_abs(STRIP_KIND); a.or_r("a"); a.jr("compose_get_pixel_strip", "z"); a.call("get_pair_microstrip_ptr"); a.jr("compose_got_strip")
    a.label("compose_get_pixel_strip"); a.call("get_microstrip_ptr")
    a.label("compose_got_strip")
    a.ld_a_abs(STRIP_PAIR); a.or_r("a"); a.jr("compose_or_strip", "nz")
    a.push("hl"); load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.call("copy_16")
    a.ld_r_r("a", "e"); a.ld_abs_a(DYN_PTR_L); a.ld_r_r("a", "d"); a.ld_abs_a(DYN_PTR_H); a.jr("compose_strip_done")
    a.label("compose_or_strip")
    a.push("hl"); load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.call("or_16")
    a.label("compose_strip_done")
    a.pop("de"); a.pop("hl")
    a.ld_a_abs(STRIP_KIND); a.inc_r("a"); a.ld_r_r("b", "a"); a.ld_a_abs(STRIP_PAIR); a.add_a_r("b"); a.ld_abs_a(STRIP_PAIR); a.cp_n(8); a.jp("compose_pair_loop", "nz")
    if SURFACE_DETAIL_ENABLED:
        a.call("apply_surface_detail")
    a.ret()

    a.label("scan_column")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(MIN_TOP); a.xor_r("a"); a.ld_abs_a(MAX_TOP); a.ld_abs_a(DARK_MASK)
    if SURFACE_DETAIL_ENABLED:
        a.ld_r_n("a", 2); a.ld_abs_a(DETAIL_MASK)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.push("hl")
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.ld_a_mem_rr("de"); a.ld_abs_a(FIRST_STYLE); a.ld_r_n("a", 8); a.ld_abs_a(CLASSIFY_COUNT)
    a.label("scan_column_loop")
    a.ldi_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(MIN_TOP); a.cp_r("b"); a.jr("scan_min_keep", "c"); a.jr("scan_min_keep", "z"); a.ld_r_r("a", "b"); a.ld_abs_a(MIN_TOP)
    a.label("scan_min_keep")
    a.ld_a_abs(MAX_TOP); a.cp_r("b"); a.jr("scan_max_keep", "nc"); a.ld_r_r("a", "b"); a.ld_abs_a(MAX_TOP)
    a.label("scan_max_keep")
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.ld_r_r("b", "a")
    # All light base styles resolve to colour 2 and all odd render styles to
    # colour 3. Build the exact eight-pixel dark mask for the static seam atlas.
    a.ld_a_abs(DARK_MASK); a.add_a_r("a"); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.and_n(1); a.or_r("c"); a.ld_abs_a(DARK_MASK)
    # Retain bit 1 only while every physical pixel is machinery material 2.
    # Mixed boundary/rib tiles conservatively omit the rail and keep using the
    # established exact atlas; this is both coherent and much cheaper than a
    # per-pixel decorative mask in the hot compositor scan.
    if SURFACE_DETAIL_ENABLED:
        a.ld_a_abs(DETAIL_MASK); a.and_r("b"); a.and_n(2); a.ld_abs_a(DETAIL_MASK)
    a.ld_a_abs(CLASSIFY_COUNT); a.dec_r("a"); a.ld_abs_a(CLASSIFY_COUNT); a.jr("scan_column_loop", "nz"); a.ret()

    a.label("classify_row")
    a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.ld_r_r("b", "a")
    a.ld_a_abs(MIN_TOP); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.cp_r("c"); a.jr("row_ceiling", "c")
    a.ld_r_n("a", 96); a.sub_r("c"); a.ld_r_r("b", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("b"); a.jr("row_floor", "nc")
    a.ld_a_abs(MAX_TOP); a.ld_r_r("c", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("c"); a.jr("row_dynamic", "c")
    a.ld_r_n("a", 96); a.sub_r("c"); a.ld_r_r("c", "a"); a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.cp_r("c"); a.jr("row_dynamic", "nc")
    if SURFACE_DETAIL_ENABLED:
        a.ld_a_abs(TILE_Y0); a.cp_n(SURFACE_RAIL_Y0); a.jr("row_static_lookup", "nz")
        a.ld_a_abs(DETAIL_MASK); a.cp_n(2); a.jr("row_static_lookup", "nz")
        a.ld_a_abs(DARK_MASK); a.or_r("a"); a.jr("row_surface_rail_light", "z"); a.cp_n(0xFF); a.jr("row_dynamic", "nz")
        a.ld_r_n("a", SURFACE_RAIL_TILE_BASE + 1); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
        a.label("row_surface_rail_light"); a.ld_r_n("a", SURFACE_RAIL_TILE_BASE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_static_lookup")
    a.ld_a_abs(DARK_MASK); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "seam_tile_lookup"); a.add_hl_rr("de"); a.ld_a_hl(); a.or_r("a"); a.jr("row_dynamic", "z")
    a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_ceiling"); a.ld_r_n("a", CEILING_TILE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_floor"); a.ld_r_n("a", FLOOR_TILE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_dynamic"); a.ld_r_n("a", 1); a.ld_abs_a(DYNAMIC_FLAG); a.ret()

    a.label("render_view")
    a.xor_r("a"); a.ld_abs_a(DYN_COUNT); a.ld_abs_a(DYN_OVERFLOW)
    a.ld_rr_nn("hl", DYNAMIC_TILES); store_hl_abs(a, DYN_PTR_L, DYN_PTR_H)
    a.ld_rr_nn("hl", VIEW_MAP); store_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H)
    a.ld_rr_nn("hl", PIXEL_TOPS); store_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    a.ld_rr_nn("hl", PIXEL_STYLES); store_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H)
    a.ld_r_n("a", 20); a.ld_abs_a(COLUMN_COUNT)
    a.label("render_column_loop")
    if FIXED_SIMULATION:
        a.call("render_yield")
    a.call("scan_column")
    a.xor_r("a"); a.ld_abs_a(TILE_ROW); a.ld_abs_a(TILE_Y0)
    load_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H); store_hl_abs(a, MAP_PTR_L, MAP_PTR_H)
    a.ld_r_n("a", 6 if FOLDED_COMPOSITOR else 12); a.ld_abs_a(ROW_RENDER_COUNT)
    a.label("render_row_loop")
    a.call("classify_row")
    a.ld_a_abs(DYNAMIC_FLAG); a.or_r("a"); a.jr("render_static_tile", "z")
    # The exact atlas key describes silhouettes and light/shadow only. A
    # decorated half-height tile therefore bypasses it and is composed exactly.
    if SURFACE_DETAIL_ENABLED:
        a.ld_a_abs(TILE_Y0); a.cp_n(SURFACE_RAIL_Y0); a.jr("render_atlas_lookup", "nz")
        a.ld_a_abs(DETAIL_MASK); a.cp_n(2); a.jr("render_dynamic_miss", "z")
    a.label("render_atlas_lookup")
    a.call("build_tile_signature"); a.call("find_atlas_tile"); a.or_r("a"); a.jr("render_dynamic_miss", "z")
    a.ld_abs_a(TILE_ID_RESULT); a.jr("render_write_tile")
    a.label("render_dynamic_miss")
    a.ld_a_abs(DYN_COUNT); a.cp_n(DYNAMIC_TILE_CAPACITY); a.jr("render_dynamic_overflow", "nc")
    a.ld_abs_a(TILE_ID_RESULT); a.call("compose_dynamic_tile")
    a.ld_a_abs(DYN_COUNT); a.inc_r("a"); a.ld_abs_a(DYN_COUNT)
    a.ld_r_r("b", "a"); a.ld_a_abs(DYN_HIGH_WATER); a.cp_r("b"); a.jr("render_dynamic_high_keep", "nc"); a.ld_r_r("a", "b"); a.ld_abs_a(DYN_HIGH_WATER)
    a.label("render_dynamic_high_keep"); a.jr("render_write_tile")
    a.label("render_dynamic_overflow")
    a.ld_r_n("a", 1); a.ld_abs_a(DYN_OVERFLOW); a.ld_r_n("a", WALL_TILE_BASE); a.ld_abs_a(TILE_ID_RESULT); a.jr("render_write_tile")
    a.label("render_static_tile")
    a.label("render_write_tile")
    if FOLDED_COMPOSITOR:
        # Mirror map position around viewport row 5.5. Patterns need neither
        # a second composition nor a second DMA; lower attrs supply Y-flip.
        a.ld_r_n("a", 11); a.ld_r_r("b", "a"); a.ld_a_abs(TILE_ROW); a.ld_r_r("c", "a")
        a.ld_r_r("a", "b"); a.sub_r("c"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
        for _ in range(5): a.add_hl_rr("hl")
        a.ld_a_abs(COLUMN_MAP_L); a.ld_r_r("e", "a"); a.ld_a_abs(COLUMN_MAP_H); a.ld_r_r("d", "a"); a.add_hl_rr("de")
        a.ld_a_abs(TILE_ID_RESULT); a.ld_hl_a()
    load_hl_abs(a, MAP_PTR_L, MAP_PTR_H); a.ld_a_abs(TILE_ID_RESULT); a.ld_hl_a(); a.ld_rr_nn("de", 32); a.add_hl_rr("de"); store_hl_abs(a, MAP_PTR_L, MAP_PTR_H)
    a.ld_a_abs(TILE_ROW); a.inc_r("a"); a.ld_abs_a(TILE_ROW)
    a.ld_a_abs(TILE_Y0); a.add_a_n(8); a.ld_abs_a(TILE_Y0)
    a.ld_a_abs(ROW_RENDER_COUNT); a.dec_r("a"); a.ld_abs_a(ROW_RENDER_COUNT); a.jp("render_row_loop", "nz")
    # Advance eight physical-pixel descriptors and one BG-map column.
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_rr_nn("de", 8); a.add_hl_rr("de"); store_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_rr_nn("de", 8); a.add_hl_rr("de"); store_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H)
    load_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H); a.inc_rr("hl"); store_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H)
    a.ld_a_abs(COLUMN_COUNT); a.dec_r("a"); a.ld_abs_a(COLUMN_COUNT); a.jp("render_column_loop", "nz"); a.ret()
