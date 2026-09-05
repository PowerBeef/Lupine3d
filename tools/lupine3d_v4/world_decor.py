"""Sparse wall-mounted fixtures, clipped by physical face/cell certificates."""
from .layout import *

FIXTURE_TILE_BASE = SENTINEL_MID_TILE_BASE + SENTINEL_MID_FRAMES * 4

def fixture_records():
    data = bytearray()
    for x,y,side,kind in ACTIVE_LEVEL.fixtures:
        px,py = x*256+128,y*256+128
        door_index = next((i for i,d in enumerate(ACTIVE_LEVEL.doors) if (d.x,d.y)==(x,y)),255)
        if door_index == 255:
            if side == 0: px -= 128
            elif side == 1: px += 128
            elif side == 2: py -= 128
            else: py += 128
        segment = ACTIVE_LEVEL.segment_table[(y*16+x)*4+side]
        assert segment
        data.extend(bytes((px&255,px>>8,py&255,py>>8,segment,kind,side,
                           y if side < 2 else x,door_index)) + bytes(7))
    return bytes(data)

def emit_world_decor(a: Assembler):
    a.label("render_wall_fixtures")
    if not ACTIVE_LEVEL.fixtures: a.ret(); return
    # The attribute packet is rebuilt after decor. Reuse its first 256 bytes
    # as a transient face-visibility table instead of rescanning 80 rays per
    # authored fixture; this does not consume additional persistent WRAM.
    a.ld_rr_nn("hl",VIEW_ATTRIBUTES); a.xor_r("a"); a.ld_r_n("b",0)
    a.label("fixture_clear_visible"); a.ldi_hl_a(); a.dec_r("b"); a.jr("fixture_clear_visible","nz")
    a.ld_rr_nn("hl",RAY_SEGMENT); a.ld_r_n("b",80); a.ld_r_n("d",VIEW_ATTRIBUTES>>8)
    a.label("fixture_mark_visible")
    a.ldi_a_hl(); a.ld_r_r("e","a"); a.ld_r_n("a",1); a.ld_mem_rr_a("de")
    a.dec_r("b"); a.jr("fixture_mark_visible","nz")
    for i in range(4): a.ld_a_abs(SENTINEL_VISIBLE+i); a.ld_abs_a(DECAL_SAVED+i)
    a.xor_r("a"); a.ld_abs_a(DECAL_INDEX); a.ld_abs_a(DECAL_USED)
    a.ld_r_n("a",1); a.ld_abs_a(DECAL_PROJECTING)
    a.label("fixture_next_record")
    a.ld_a_abs(DECAL_INDEX); a.cb("swap","a"); a.ld_r_r("e","a"); a.ld_r_n("d",0)
    a.ld_rr_label("hl","wall_fixture_records"); a.add_hl_rr("de")
    for _ in range(4): a.inc_rr("hl")
    a.ld_a_hl(); a.ld_r_r("e","a"); a.ld_r_n("d",VIEW_ATTRIBUTES>>8)
    a.ld_a_mem_rr("de"); a.or_r("a"); a.jp("fixture_advance","z")
    for _ in range(4): a.dec_rr("hl")
    a.ld_rr_nn("de",DECAL_RECORD); a.ld_rr_nn("bc",9); a.call("copy_bc")
    a.label("fixture_face_visible")
    for i in range(4): a.ld_a_abs(DECAL_RECORD+i); a.ld_abs_a(ENTITY_WORLD_XL+i)
    # Door emblems ride their panel and disappear into its jamb.
    a.ld_a_abs(DECAL_RECORD+8); a.cp_n(255); a.jr("fixture_project","z")
    a.ld_r_r("b","a"); a.add_a_r("a"); a.add_a_r("b"); a.add_a_r("a")
    a.ld_r_r("e","a"); a.ld_r_n("d",0); a.ld_rr_nn("hl",DOOR_TABLE+DOOR_FRACTION_OFFSET); a.add_hl_rr("de")
    a.ld_a_hl(); a.cp_n(128); a.jp("fixture_advance","nc"); a.ld_r_r("b","a")
    a.ld_a_abs(DECAL_RECORD+6); a.cp_n(2); a.jr("fixture_door_y","c")
    a.ld_a_abs(ENTITY_WORLD_XL); a.add_a_r("b"); a.ld_abs_a(ENTITY_WORLD_XL); a.jr("fixture_project")
    a.label("fixture_door_y"); a.ld_a_abs(ENTITY_WORLD_YL); a.add_a_r("b"); a.ld_abs_a(ENTITY_WORLD_YL)
    a.label("fixture_project"); a.call("project_entity")
    a.ld_a_abs(SENTINEL_VISIBLE); a.or_r("a"); a.jp("fixture_advance","z")
    a.ld_a_abs(ENTITY_FOOT_Y); a.sub_n(64); a.cp_n(6); a.jp("fixture_advance","c")
    a.ld_r_r("b","a"); a.cb("srl","a"); a.ld_r_r("c","a")
    a.ld_r_n("a",64); a.sub_r("c"); a.ld_abs_a(DECAL_Y)
    a.ld_r_n("d",16); a.ld_r_n("e",0)
    a.ld_r_r("a","b"); a.cp_n(24); a.jr("fixture_size_ready","nc")
    a.ld_r_n("d",8); a.ld_r_n("e",4); a.cp_n(12); a.jr("fixture_size_ready","nc")
    a.ld_r_n("d",4); a.ld_r_n("e",6)
    a.label("fixture_size_ready")
    a.ld_r_r("a","d"); a.ld_abs_a(DECAL_HEIGHT); a.cp_n(16); a.ld_r_n("a",0); a.jr("fixture_width_ready","nz")
    # Compress horizontally at oblique angles; suppress near-tangent decals.
    a.ld_a_abs(DECAL_RECORD+6); a.cp_n(2); a.ld_a_abs(ENTITY_SIN); a.jr("fixture_normal_ready","nc")
    a.ld_a_abs(ENTITY_COS); a.label("fixture_normal_ready")
    a.cb("bit","a",7); a.jr("fixture_normal_abs","z"); a.cpl(); a.inc_r("a")
    a.label("fixture_normal_abs"); a.cp_n(16); a.jp("fixture_advance","c")
    a.cp_n(45); a.ld_r_n("a",1); a.jr("fixture_width_ready","nc")
    a.ld_r_n("e",8); a.xor_r("a")
    a.label("fixture_width_ready"); a.ld_abs_a(DECAL_WIDE)
    a.ld_a_abs(DECAL_RECORD+5); a.cb("swap","a"); a.add_a_n(FIXTURE_TILE_BASE); a.add_a_r("e"); a.ld_abs_a(DECAL_SOURCE)
    a.ld_a_abs(DECAL_HEIGHT); a.cb("srl","a"); a.ld_r_r("b","a"); a.ld_a_abs(DECAL_Y); a.sub_r("b"); a.ld_abs_a(DECAL_Y)
    a.xor_r("a"); a.ld_abs_a(DECAL_COLUMN)
    a.label("fixture_draw_column")
    a.ld_a_abs(DECAL_USED); a.cp_n(4); a.jp("fixture_done","nc")
    a.ld_a_abs(DECAL_WIDE); a.or_r("a"); a.ld_r_n("b",4); a.jr("fixture_x_base","z"); a.ld_r_n("b",0)
    a.label("fixture_x_base"); a.ld_a_abs(DECAL_COLUMN); a.add_a_r("a"); a.add_a_r("a"); a.add_a_r("a"); a.add_a_r("b"); a.ld_r_r("b","a")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.add_a_r("b"); a.ld_abs_a(MASK_OAM_X); a.sub_n(8); a.call("fixture_mask")
    a.ld_abs_a(MASK_BITS); a.or_r("a"); a.jr("fixture_next_column","z")
    a.ld_a_abs(DECAL_Y); a.ld_r_r("b","a"); a.ld_a_abs(MASK_OAM_X); a.ld_r_r("c","a")
    a.ld_a_abs(DECAL_COLUMN); a.add_a_r("a"); a.ld_r_r("d","a"); a.ld_a_abs(DECAL_SOURCE); a.add_a_r("d"); a.ld_r_r("d","a")
    a.ld_a_abs(DECAL_RECORD+5); a.cp_n(2); a.ld_r_n("e",3); a.jr("fixture_palette_ready","nz"); a.ld_r_n("e",4)
    a.label("fixture_palette_ready"); a.call("submit_masked_oam")
    a.ld_a_abs(DECAL_USED); a.inc_r("a"); a.ld_abs_a(DECAL_USED)
    a.label("fixture_next_column")
    a.ld_a_abs(DECAL_WIDE); a.or_r("a"); a.jr("fixture_advance","z")
    a.ld_a_abs(DECAL_COLUMN); a.inc_r("a"); a.ld_abs_a(DECAL_COLUMN); a.cp_n(2); a.jp("fixture_draw_column","c")
    a.label("fixture_advance")
    a.ld_a_abs(DECAL_INDEX); a.inc_r("a"); a.ld_abs_a(DECAL_INDEX); a.cp_n(len(ACTIVE_LEVEL.fixtures)); a.jp("fixture_next_record","c")
    a.label("fixture_done")
    a.xor_r("a"); a.ld_abs_a(DECAL_PROJECTING)
    for i in range(4): a.ld_a_abs(DECAL_SAVED+i); a.ld_abs_a(SENTINEL_VISIBLE+i)
    a.ret()

    a.label("fixture_mask")  # A = physical left X; segment AND cell stencil
    a.ld_abs_a(ENTITY_TMP_L); a.ld_r_n("a",8); a.ld_abs_a(ENTITY_TMP_H); a.xor_r("a"); a.ld_abs_a(MASK_BITS)
    a.label("fixture_mask_pixel")
    a.ld_a_abs(MASK_BITS); a.add_a_r("a"); a.ld_abs_a(MASK_BITS)
    a.ld_a_abs(ENTITY_TMP_L); a.cp_n(160); a.jr("fixture_mask_next","nc")
    a.ld_r_r("e","a"); a.ld_r_n("d",0); a.ld_rr_nn("hl",PIXEL_SEGMENT); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b","a")
    a.ld_a_abs(DECAL_RECORD+4); a.cp_r("b"); a.jr("fixture_mask_next","nz")
    a.ld_rr_nn("hl",PIXEL_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b","a")
    a.ld_a_abs(DECAL_RECORD+7); a.cp_r("b"); a.jr("fixture_mask_next","nz")
    a.ld_a_abs(MASK_BITS); a.or_n(1); a.ld_abs_a(MASK_BITS)
    a.label("fixture_mask_next")
    a.ld_a_abs(ENTITY_TMP_L); a.inc_r("a"); a.ld_abs_a(ENTITY_TMP_L)
    a.ld_a_abs(ENTITY_TMP_H); a.dec_r("a"); a.ld_abs_a(ENTITY_TMP_H); a.jr("fixture_mask_pixel","nz")
    a.ld_a_abs(MASK_BITS); a.ret()
