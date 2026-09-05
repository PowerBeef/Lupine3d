"""Atomic actor admission against actual Y-selected hardware objects.

Four prospective strips are staged in fixed WRAM. Preflight mutates no world
allocation state. Temporary capacity LOD never changes distance hysteresis.
"""
from .layout import *


def emit_admission(a: Assembler):
    if not (SCANLINE_ADMISSION or SABLE_ART): return
    a.label("seed_foreground_scanlines")
    # Predict the submitted muzzle without decrementing the snapshot's FLASH.
    # A foreground event may activate it between world commits, so that mode
    # reserves its maximum Y occupancy even while the current flash is hidden.
    if not FOREGROUND_PUBLICATION:
        a.ld_a_abs(FLASH); a.or_r("a"); a.ld_r_n("a",0); a.jr("seed_muzzle_ready","z"); a.ld_r_n("a",VIEW_HEIGHT - 24)
        a.label("seed_muzzle_ready"); a.ld_abs_a(OAM_SHADOW+9*4)
    for index in range(ENTITY_OAM_FIRST):
        end=f"seed_ui_{index}_done"
        if FOREGROUND_PUBLICATION and index==9: a.ld_r_n("a",VIEW_HEIGHT - 24)
        else: a.ld_a_abs(OAM_SHADOW+index*4)
        a.or_r("a"); a.jr(end,"z"); a.cp_n(160); a.jr(end,"nc")
        a.ld_r_r("c","a"); a.sub_n(16); a.jr(f"seed_ui_{index}_start","nc"); a.xor_r("a")
        a.label(f"seed_ui_{index}_start"); a.ld_r_r("l","a"); a.ld_r_n("h",WORLD_SCANLINES>>8)
        a.ld_r_r("a","c"); a.cp_n(144); a.jr(f"seed_ui_{index}_end","c"); a.ld_r_n("a",144)
        a.label(f"seed_ui_{index}_end"); a.sub_r("l"); a.ld_r_r("c","a")
        a.label(f"seed_ui_{index}_loop"); a.inc_r("(hl)"); a.inc_rr("hl"); a.dec_r("c"); a.jr(f"seed_ui_{index}_loop","nz")
        a.label(end)
    a.ret()

    a.label("collect_actor_strip")  # submit arguments already staged in MASK_*; preserve allocation state
    a.ld_a_abs(MASK_BITS); a.or_r("a"); a.ret("z")
    a.ld_a_abs(MASK_OAM_Y); a.or_r("a"); a.ret("z"); a.cp_n(160); a.ret("nc")
    a.ld_a_abs(ADMISSION_COUNT); a.cp_n(4); a.jr("admission_collect_overflow","nc")
    a.ld_r_r("e","a"); a.add_a_r("a"); a.add_a_r("a"); a.add_a_r("e"); a.add_a_n(ADMISSION_RECORDS&255); a.ld_r_r("l","a"); a.ld_r_n("h",ADMISSION_RECORDS>>8)
    for address in (MASK_OAM_Y,MASK_OAM_X,MASK_SOURCE_TILE,MASK_ATTRIBUTES,MASK_BITS): a.ld_a_abs(address); a.ldi_hl_a()
    a.ld_rr_nn("hl",ADMISSION_COUNT); a.inc_r("(hl)"); a.ret()
    a.label("admission_collect_overflow"); a.ld_r_n("a",1); a.ld_abs_a(ADMISSION_FAILED); a.ret()

    a.label("preflight_actor")  # A=1 pass, 0 fail. No reservations made here.
    a.ld_a_abs(ADMISSION_FAILED); a.or_r("a"); a.jr("admission_fail","nz")
    a.ld_a_abs(ADMISSION_COUNT); a.ld_r_r("b","a"); a.ld_a_abs(SENTINEL_OAM_USED); a.add_a_r("b"); a.cp_n(ENTITY_OAM_COUNT+1); a.jr("admission_fail","nc")
    a.ld_r_r("a","b"); a.add_a_r("a"); a.ld_r_r("b","a"); a.ld_a_abs(MASK_TILE_COUNT); a.add_a_r("b"); a.cp_n(33); a.jr("admission_fail","nc")
    a.xor_r("a"); a.ld_abs_a(ADMISSION_LINE)
    a.label("admission_line_loop")
    a.ld_a_abs(ADMISSION_LINE); a.ld_r_r("l","a"); a.ld_r_n("h",WORLD_SCANLINES>>8); a.ld_a_hl(); a.ld_r_r("b","a")
    a.ld_a_abs(ADMISSION_COUNT); a.ld_r_r("c","a"); a.or_r("a"); a.jr("admission_line_ready","z")
    a.ld_rr_nn("hl",ADMISSION_RECORDS)
    a.label("admission_count_overlap")
    a.ld_a_hl(); a.ld_r_r("e","a"); a.ld_a_abs(ADMISSION_LINE); a.cp_r("e"); a.jr("admission_strip_next","nc")
    a.add_a_n(16); a.cp_r("e"); a.jr("admission_strip_next","c"); a.inc_r("b")
    a.label("admission_strip_next")
    a.ld_rr_nn("de",5); a.add_hl_rr("de"); a.dec_r("c"); a.jr("admission_count_overlap","nz")
    a.label("admission_line_ready")
    a.ld_r_r("a","b"); a.cp_n(11 if SCANLINE_ADMISSION else 5); a.jr("admission_fail","nc")
    a.ld_rr_nn("hl",ADMISSION_LINE); a.inc_r("(hl)"); a.ld_a_hl(); a.cp_n(144); a.jr("admission_line_loop","c")
    a.ld_r_n("a",1); a.ret()
    a.label("admission_fail"); a.xor_r("a"); a.ret()

    a.label("render_actor_atomic")
    a.ld_a_abs(SENTINEL_LOD); a.ld_abs_a(ADMISSION_DISTANCE_LOD)
    a.label("admission_retry_lod")
    a.xor_r("a"); a.ld_abs_a(ADMISSION_COUNT); a.ld_abs_a(ADMISSION_FAILED)
    a.ld_r_n("a",1); a.ld_abs_a(ADMISSION_MODE)
    a.call("render_actor_selected_lod")
    a.xor_r("a"); a.ld_abs_a(ADMISSION_MODE)
    a.call("preflight_actor"); a.or_r("a"); a.jr("admission_commit","nz")
    a.label("admission_capacity_rejected")
    a.ld_a_abs(SENTINEL_LOD); a.cp_n(2); a.jr("admission_restore_lod","z")
    a.inc_r("a"); a.ld_abs_a(SENTINEL_LOD); a.cp_n(2); a.jr("admission_retry_lod","nz")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.call("entity_column_visible"); a.ld_abs_a(ENTITY_SCREEN_LEFT)
    a.jr("admission_retry_lod")
    a.label("admission_commit")
    a.xor_r("a"); a.ld_abs_a(ADMISSION_INDEX)
    a.label("admission_commit_loop")
    a.ld_a_abs(ADMISSION_COUNT); a.ld_r_r("b","a"); a.ld_a_abs(ADMISSION_INDEX); a.cp_r("b"); a.jr("admission_restore_lod","nc")
    a.ld_r_r("e","a"); a.add_a_r("a"); a.add_a_r("a"); a.add_a_r("e"); a.add_a_n(ADMISSION_RECORDS&255); a.ld_r_r("l","a"); a.ld_r_n("h",ADMISSION_RECORDS>>8)
    for r in ("b","c","d","e"): a.ldi_a_hl(); a.ld_r_r(r,"a")
    a.ld_a_hl(); a.ld_abs_a(MASK_BITS); a.call("submit_masked_oam")
    a.ld_rr_nn("hl",ADMISSION_INDEX); a.inc_r("(hl)"); a.jr("admission_commit_loop")
    a.label("admission_restore_lod")
    a.ld_a_abs(ADMISSION_DISTANCE_LOD); a.ld_abs_a(SENTINEL_LOD); a.ret()
