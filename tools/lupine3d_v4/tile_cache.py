"""Exact persistent pattern cache; allocation order remains compositor-owned.

Bank-3 entries: valid, profile, generation[2], signature[10], pattern[16],
reserved[2]. Only the complete key is authoritative; hash selects a victim.
The fixed staging range survives selecting bank 3. No routine yields there.
"""
from .layout import *


def emit_tile_cache(a: Assembler):
    if not DYNAMIC_TILE_CACHE: return
    a.label("clear_dynamic_cache")
    # Reload runs in either the snapshot or live bank. Preserve the caller's
    # bank here; the hot cache routines below always return with bank 1.
    a.ldh_a_n(SVBK); a.push("af")
    a.ld_r_n("a", 3); a.ldh_n_a(SVBK)
    a.ld_rr_nn("hl", 0xD000); a.ld_rr_nn("de", 32); a.ld_r_n("b", 128); a.xor_r("a")
    a.label("clear_dynamic_cache_entry")
    a.ld_hl_a(); a.add_hl_rr("de"); a.dec_r("b"); a.jr("clear_dynamic_cache_entry", "nz")
    a.pop("af"); a.ldh_n_a(SVBK); a.ret()

    a.label("compose_dynamic_tile_cached")
    # Stage profile, generation and all ten signature bytes before banking.
    a.ld_rr_nn("hl", DYNAMIC_CACHE_STAGE + 1)
    for address in (VRAM_PROFILE, WALL_EPOCH, WALL_EPOCH+1, TILE_Y0, DARK_MASK):
        a.ld_a_abs(address); a.ldi_hl_a()
    a.ld_rr_nn("de", DYNAMIC_CACHE_STAGE + 6)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    a.ld_r_n("b", 8)
    a.label("dynamic_cache_stage_tops")
    a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de"); a.dec_r("b"); a.jr("dynamic_cache_stage_tops", "nz")
    a.ld_a_abs(SIGNATURE_HASH)
    if CACHE_KEY_MIX:
        # Eight equal tops cancel in the atlas's rotate/XOR hash. Mixing the
        # first top spreads flat silhouettes without weakening full-key checks.
        a.ld_r_r("b", "a"); a.ld_a_abs(DYNAMIC_CACHE_STAGE+6); a.xor_r("b")
    a.and_n(127); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(5): a.add_hl_rr("hl")
    a.ld_rr_nn("de", 0xD000); a.add_hl_rr("de")
    store_hl_abs(a, DYNAMIC_CACHE_POINTER, DYNAMIC_CACHE_POINTER+1)
    a.ld_r_n("a", 3); a.ldh_n_a(SVBK)
    a.ldi_a_hl(); a.cp_n(1); a.jr("dynamic_cache_miss", "nz")
    a.ld_rr_nn("de", DYNAMIC_CACHE_STAGE+1); a.ld_r_n("b", 13)
    a.label("dynamic_cache_compare")
    a.ld_a_mem_rr("de"); a.cp_r("(hl)"); a.jr("dynamic_cache_miss", "nz")
    a.inc_rr("hl"); a.inc_rr("de"); a.dec_r("b"); a.jr("dynamic_cache_compare", "nz")
    a.label("dynamic_cache_hit")
    a.push("hl"); load_hl_abs(a, DYN_PTR_L, DYN_PTR_H)
    a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.call("copy_16")
    a.ld_r_r("a", "e"); a.ld_abs_a(DYN_PTR_L); a.ld_r_r("a", "d"); a.ld_abs_a(DYN_PTR_H)
    a.ld_r_n("a", 1); a.ldh_n_a(SVBK); a.ret()

    a.label("dynamic_cache_miss")
    a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
    a.call("compose_dynamic_tile")
    # Validity is cleared before replacement and committed after the complete
    # metadata and pattern. VBlank may interrupt any instruction safely.
    load_hl_abs(a, DYNAMIC_CACHE_POINTER, DYNAMIC_CACHE_POINTER+1)
    a.ld_r_n("a", 3); a.ldh_n_a(SVBK); a.xor_r("a"); a.ldi_hl_a()
    a.ld_r_r("d", "h"); a.ld_r_r("e", "l")
    a.ld_rr_nn("hl", DYNAMIC_CACHE_STAGE+1); a.ld_rr_nn("bc", 13); a.call("copy_bc")
    load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.call("copy_16")
    load_hl_abs(a, DYNAMIC_CACHE_POINTER, DYNAMIC_CACHE_POINTER+1)
    a.ld_r_n("a", 1); a.ld_hl_a(); a.ldh_n_a(SVBK); a.ret()
