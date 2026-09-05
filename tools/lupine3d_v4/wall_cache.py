"""Exact whole-view reuse and independent entity/HUD publication.

No checksums or approximate pose tolerances: every mutable wall input is
compared byte-for-byte. Keys are captured before rendering yields, so a live
world update cannot certify an older render as a newer view.
"""
from .layout import *


WALL_KEY_RANGES = ((PLAYER_XL, WALL_CACHE_META, 5),
                   (VRAM_PROFILE, WALL_CACHE_META + 5, 2),
                   (DOOR_COUNT, WALL_CACHE_META + 7, 1),
                   (DOOR_TABLE, WALL_CACHE_META + 8, MAX_DOORS * DOOR_RECORD_BYTES),
                   (WALL_EPOCH, WALL_CACHE_META + 32, 2),
                   (MAP, WALL_CACHE_MAP, 256))


def emit_wall_cache(a: Assembler):
    a.labels["presentation_serial"] = PRESENT_SERIAL
    a.label("invalidate_wall_cache")
    if FOREGROUND_PUBLICATION: a.call("foreground_reset")
    if DYNAMIC_TILE_CACHE:
        # Every content/profile reload clears validity, including the u16
        # generation-wrap case; no stale generation can become current again.
        a.call("clear_dynamic_cache")
    a.xor_r("a"); a.ld_abs_a(WALL_CACHE_VALID)
    a.ld_rr_nn("hl", WALL_EPOCH); a.inc_r("(hl)"); a.ret("nz")
    a.inc_rr("hl"); a.inc_r("(hl)"); a.ret()

    a.label("check_wall_reuse")
    a.xor_r("a"); a.ld_abs_a(FRAME_REUSED)
    if PHYSICAL_DEPTH: a.ld_abs_a(GEOMETRY_BACKBONE_RAN)
    if WALL_REUSE_ENABLED:
        a.ld_a_abs(WALL_CACHE_DISABLE); a.or_r("a"); a.jp("wall_cache_miss", "nz")
        a.ld_a_abs(WALL_CACHE_VALID); a.or_r("a"); a.jp("wall_cache_miss", "z")
        for source, key, count in WALL_KEY_RANGES:
            a.ld_rr_nn("hl", source); a.ld_rr_nn("de", key); a.ld_r_n("b", count & 255)
            a.call("wall_key_equal"); a.jp("wall_cache_miss", "nz")
        a.ld_r_n("a", 1); a.ld_abs_a(FRAME_REUSED); a.ret()
    a.label("wall_cache_miss")
    a.xor_r("a"); a.ld_abs_a(WALL_CACHE_VALID)
    for source, key, count in WALL_KEY_RANGES:
        a.ld_rr_nn("hl", source); a.ld_rr_nn("de", key); a.ld_rr_nn("bc", count); a.call("copy_bc")
    a.xor_r("a"); a.ret()

    a.label("wall_key_equal")  # B=0 compares exactly 256 bytes
    a.ld_a_mem_rr("de"); a.cp_r("(hl)"); a.ret("nz")
    a.inc_rr("hl"); a.inc_rr("de"); a.dec_r("b"); a.jr("wall_key_equal", "nz")
    a.xor_r("a"); a.ret()

    a.label("upload_entities_hud")
    if FOREGROUND_PUBLICATION: a.call("prepare_foreground_commit")
    a.call("prepare_hud_tiles"); a.call("wait_vblank")
    # Only the hidden OBJ bank changes. The displayed BG map, attributes and
    # dynamic patterns are untouched, even if the two page owners disagree.
    a.call("upload_masked_tiles"); a.call("update_hud_tiles")
    a.call("update_muzzle_oam"); a.call("publish_oam_packet")
    if ENABLE_MICRO_REPROJECTION: a.call("reset_reprojection_for_commit")
    a.jp("finish_presentation")

    a.label("finish_presentation")
    a.ld_a_abs(OBJ_PAGE); a.xor_n(1); a.ld_abs_a(OBJ_PAGE)
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_rr_nn("hl", PRESENT_SERIAL); a.inc_r("(hl)")
    if FOREGROUND_PUBLICATION: a.jp("finish_foreground_commit")
    else: a.ret()
