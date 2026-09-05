"""Optional Q8.8 actor transform with signed Q14 camera products.

All scratch belongs to the caller's world bank (snapshot 1 or live 2).
No cooperative yield occurs inside a transform. Products and sums use signed
32-bit two's complement; rounding to Q8.8 happens once, ties toward +infinity.
The original projection remains linked as an independently callable oracle.
"""
from .layout import *


def _load_pair(a,address,pair="hl"):
    low,high={"hl":("l","h"),"de":("e","d")}[pair]
    a.ld_a_abs(address); a.ld_r_r(low,"a"); a.ld_a_abs(address+1); a.ld_r_r(high,"a")


def emit_actor_precision(a: Assembler):
    if not ACTOR_PRECISION: return
    a.label("actor_product_signed")  # signed HL*DE -> Q14_PRODUCT, all registers clobbered
    a.ld_r_r("a","h"); a.xor_r("d"); a.ld_abs_a(ACTOR_SIGN)
    a.cb("bit","h",7); a.jr("actor_product_hl_positive","z"); a.call("negate_hl")
    a.label("actor_product_hl_positive")
    a.cb("bit","d",7); a.jr("actor_product_de_positive","z")
    a.ld_r_r("a","e"); a.cpl(); a.add_a_n(1); a.ld_r_r("e","a")
    a.ld_r_r("a","d"); a.cpl(); a.adc_a_n(0); a.ld_r_r("d","a")
    a.label("actor_product_de_positive"); a.call("q14_multiply_u16")
    a.ld_a_abs(ACTOR_SIGN); a.cb("bit","a",7); a.ret("z")
    for i in range(4):
        a.ld_a_abs(Q14_PRODUCT+i); a.cpl()
        (a.add_a_n if i==0 else a.adc_a_n)(1 if i==0 else 0); a.ld_abs_a(Q14_PRODUCT+i)
    a.ret()

    a.label("actor_round_transform")  # (signed accumulator + product) / 2^14 -> HL
    for i in range(4):
        a.ld_a_abs(ACTOR_ACCUM+i); a.ld_r_r("b","a"); a.ld_a_abs(Q14_PRODUCT+i)
        (a.add_a_r if i==0 else a.adc_a_r)("b"); a.ld_abs_a(ACTOR_ACCUM+i)
    a.ld_a_abs(ACTOR_ACCUM+1); a.add_a_n(32); a.ld_abs_a(ACTOR_ACCUM+1)
    for i in (2,3): a.ld_a_abs(ACTOR_ACCUM+i); a.adc_a_n(0); a.ld_abs_a(ACTOR_ACCUM+i)
    a.ld_r_n("b",14)
    a.label("actor_round_shift")
    a.ld_rr_nn("hl",ACTOR_ACCUM+3); a.cb("sra","(hl)")
    for _ in range(3): a.dec_rr("hl"); a.cb("rr","(hl)")
    a.dec_r("b"); a.jr("actor_round_shift","nz"); _load_pair(a,ACTOR_ACCUM); a.ret()

    a.label("actor_project_ratio")  # unsigned Q14_PRODUCT / forward, nearest -> Q14_PRODUCT
    _load_pair(a,ACTOR_FORWARD_Q8,"de")
    a.ld_r_r("h","d"); a.ld_r_r("l","e"); a.cb("srl","h"); a.cb("rr","l")
    for i,r in enumerate(("l","h")):
        a.ld_a_abs(Q14_PRODUCT+i); (a.add_a_r if i==0 else a.adc_a_r)(r); a.ld_abs_a(Q14_PRODUCT+i)
    for i in (2,3): a.ld_a_abs(Q14_PRODUCT+i); a.adc_a_n(0); a.ld_abs_a(Q14_PRODUCT+i)
    a.jp("divide_u32_u16")

    a.label("project_entity_q8")
    a.xor_r("a"); a.ld_abs_a(SENTINEL_VISIBLE)
    a.ld_r_n("a",255); a.ld_abs_a(SENTINEL_SCREEN_X)
    for name,entity,player,dest in (("dx",ENTITY_WORLD_XL,PLAYER_XL,ACTOR_DX_Q8),("dy",ENTITY_WORLD_YL,PLAYER_YL,ACTOR_DY_Q8)):
        for i in range(2):
            a.ld_a_abs(player+i); a.ld_r_r("b","a"); a.ld_a_abs(entity+i)
            (a.sub_r if i==0 else a.sbc_a_r)("b"); a.ld_abs_a(dest+i)
        a.ld_a_abs(dest+1); a.add_a_n(8); a.cp_n(16); a.jp("project_entity_hidden","nc")
    # Retain the scale-64 basis consumed by fixture-facing classification.
    a.ld_a_abs(ANGLE); a.ld_r_r("e","a"); a.ld_r_n("d",0)
    a.ld_rr_label("hl","step_dx"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ENTITY_COS)
    a.ld_rr_label("hl","step_dy"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ENTITY_SIN)
    # Record 240 is the camera axis, including every quadrant and yaw wrap.
    a.ld_a_abs(ANGLE); a.cb("swap","a"); a.and_n(15); a.add_a_n(Q14_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_a_abs(ANGLE); a.and_n(15); a.add_a_r("a"); a.add_a_r("a"); a.add_a_n(0x43); a.ld_r_r("h","a"); a.ld_r_n("l",0xC0)
    for i in range(4): a.ldi_a_hl(); a.ld_abs_a(ACTOR_COS_Q14+i)
    a.ld_r_n("a",1); a.ld_abs_a(0x2000)
    for name,first,second,dest in (
        ("forward",(ACTOR_DX_Q8,ACTOR_COS_Q14),(ACTOR_DY_Q8,ACTOR_SIN_Q14),ACTOR_FORWARD_Q8),
        ("lateral",(ACTOR_DX_Q8,ACTOR_SIN_Q14),(ACTOR_DY_Q8,ACTOR_COS_Q14),ACTOR_LATERAL_Q8)):
        _load_pair(a,first[0]); _load_pair(a,first[1],"de")
        if name=="lateral": a.call("negate_hl")
        a.call("actor_product_signed")
        for i in range(4): a.ld_a_abs(Q14_PRODUCT+i); a.ld_abs_a(ACTOR_ACCUM+i)
        _load_pair(a,second[0]); _load_pair(a,second[1],"de"); a.call("actor_product_signed"); a.call("actor_round_transform")
        store_hl_abs(a,dest,dest+1)
    _load_pair(a,ACTOR_FORWARD_Q8)
    a.ld_r_r("a","h"); a.cp_n(8); a.jp("project_entity_hidden","nc"); a.or_r("a"); a.jr("actor_forward_valid","nz")
    a.ld_r_r("a","l"); a.cp_n(80); a.jp("project_entity_hidden","c")
    a.label("actor_forward_valid")
    for _ in range(4): a.cb("srl","h"); a.cb("rr","l")
    a.ld_r_r("a","l"); a.ld_abs_a(ENTITY_FORWARD)  # unchanged distance/LOD thresholds
    _load_pair(a,ACTOR_FORWARD_Q8); a.ld_rr_nn("de",4); a.add_hl_rr("de")
    for _ in range(3): a.cb("srl","h"); a.cb("rr","l")
    a.ld_r_r("a","h"); a.or_r("a"); a.ld_r_n("a",255); a.jr("actor_depth_store","nz"); a.ld_r_r("a","l")
    a.label("actor_depth_store"); a.ld_abs_a(SENTINEL_DEPTH)
    _load_pair(a,ACTOR_LATERAL_Q8)
    a.ld_r_r("a","h"); a.ld_abs_a(ACTOR_SCREEN_SIGN); a.cb("bit","h",7); a.jr("actor_screen_positive","z"); a.call("negate_hl")
    a.label("actor_screen_positive")
    a.ld_r_r("a","h"); a.cp_n(8); a.jp("project_entity_hidden","nc")
    a.ld_rr_nn("de",CAMERA_FOCAL_PIXELS); a.call("q14_multiply_u16"); a.call("actor_project_ratio")
    a.ld_a_abs(Q14_PRODUCT+1); a.or_r("a"); a.jp("project_entity_hidden","nz")
    a.ld_a_abs(Q14_PRODUCT); a.cp_n(88); a.jp("project_entity_hidden","nc"); a.ld_r_r("b","a")
    a.ld_a_abs(ACTOR_SCREEN_SIGN); a.cb("bit","a",7); a.ld_r_n("a",80); a.jr("actor_screen_right","z")
    a.sub_r("b"); a.jr("actor_screen_store")
    a.label("actor_screen_right"); a.add_a_r("b")
    a.label("actor_screen_store"); a.ld_abs_a(SENTINEL_SCREEN_X)
    a.ld_a_abs(DECAL_PROJECTING); a.or_r("a"); a.jr("actor_precision_foot","nz"); a.call("choose_entity_lod")
    a.label("actor_precision_foot")
    for i,value in enumerate((0,30,0,0)): a.ld_r_n("a",value); a.ld_abs_a(Q14_PRODUCT+i)  # 30*256
    a.call("actor_project_ratio"); a.ld_a_abs(Q14_PRODUCT); a.add_a_n(HORIZON); a.cp_n(VIEW_HEIGHT+1)
    a.jp("entity_foot_in_view","c"); a.ld_r_n("a",VIEW_HEIGHT); a.jp("entity_foot_in_view")
