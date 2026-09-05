"""Bounded near-field experiment: selected Q14 plane, final Q8 rounding.

Far-field and raw gameplay probes retain the legacy Q5 projection. This is a
fixed arithmetic candidate, independent of projection-table storage format.
"""
from .layout import *


@lru_cache(maxsize=1)
def near_corrections():
    focal=80/math.tan(math.radians(FOV_DEGREES/2))
    positions=[2*i+1 for i in range(80)]+[i+.5 for i in range(160)]+[80]
    return tuple(round(16384/math.sqrt(1+((x-80)/focal)**2)) for x in positions)


def project_near_reference(distance,component,record,legacy_top,legacy_depth):
    if record>240 or legacy_depth>=64 or not component: return legacy_top,legacy_depth
    perpendicular=(distance*near_corrections()[record]+component//2)//component
    if perpendicular>=512:return legacy_top,legacy_depth
    half=min(48,(7680+max(1,perpendicular)//2)//max(1,perpendicular))
    return 48-half,min(255,(perpendicular+4)//8)


def emit_near_field(a: Assembler):
    if not NEAR_FIELD:return
    a.label("near_round_divide")  # unsigned Q14_PRODUCT / DE, nearest
    a.ld_r_r("h","d");a.ld_r_r("l","e");a.cb("srl","h");a.cb("rr","l")
    for i,r in enumerate(("l","h")):
        a.ld_a_abs(Q14_PRODUCT+i);(a.add_a_r if i==0 else a.adc_a_r)(r);a.ld_abs_a(Q14_PRODUCT+i)
    for i in (2,3):a.ld_a_abs(Q14_PRODUCT+i);a.adc_a_n(0);a.ld_abs_a(Q14_PRODUCT+i)
    a.jp("divide_u32_u16")

    a.label("refine_near_projection")
    a.ld_a_abs(Q14_RECORD);a.cp_n(241);a.ret("nc")
    a.ld_a_abs(DEPTH_RESULT);a.cp_n(64);a.ret("nc")
    a.call("q14_load_door_components")
    a.ld_a_abs(Q14_RECORD);a.ld_r_r("e","a");a.ld_r_n("d",0)
    a.ld_rr_label("hl","near_correction_q14");a.add_hl_rr("de");a.add_hl_rr("de")
    a.ldi_a_hl();a.ld_r_r("e","a");a.ld_a_hl();a.ld_r_r("d","a")
    load_hl_abs(a,DDA_DIST_L,DDA_DIST_H);a.call("q14_multiply_u16")
    a.ld_rr_nn("hl",Q14_X);a.ld_a_abs(DDA_AXIS);a.or_r("a");a.jr("near_component_selected","z")
    a.ld_rr_nn("hl",Q14_Y)
    a.label("near_component_selected")
    a.ldi_a_hl();a.ld_r_r("e","a");a.ld_a_hl();a.ld_r_r("d","a");a.or_r("e");a.ret("z")
    a.call("near_round_divide")
    a.ld_a_abs(Q14_PRODUCT+2);a.ld_r_r("b","a");a.ld_a_abs(Q14_PRODUCT+3);a.or_r("b");a.ret("nz")
    a.ld_a_abs(Q14_PRODUCT+1);a.cp_n(2);a.ret("nc")
    a.ld_r_r("h","a");a.ld_a_abs(Q14_PRODUCT);a.ld_r_r("l","a");store_hl_abs(a,NEAR_PERP_Q8,NEAR_PERP_Q8+1)
    a.ld_rr_nn("de",4);a.add_hl_rr("de")
    for _ in range(3):a.cb("srl","h");a.cb("rr","l")
    a.ld_r_r("a","l");a.ld_abs_a(DEPTH_RESULT)
    a.ld_a_abs(NEAR_PERP_Q8);a.ld_r_r("e","a");a.ld_a_abs(NEAR_PERP_Q8+1);a.ld_r_r("d","a");a.or_r("e");a.jr("near_positive_depth","nz");a.inc_r("e")
    a.label("near_positive_depth")
    for i,v in enumerate((0,30,0,0)):a.ld_r_n("a",v);a.ld_abs_a(Q14_PRODUCT+i)
    a.call("near_round_divide")
    a.ld_a_abs(Q14_PRODUCT+1);a.or_r("a");a.jr("near_clipped","nz")
    a.ld_a_abs(Q14_PRODUCT);a.cp_n(49);a.jr("near_clipped","nc")
    a.ld_r_r("b","a");a.ld_r_n("a",48);a.sub_r("b");a.ld_abs_a(TOP_RESULT);a.ret()
    a.label("near_clipped");a.xor_r("a");a.ld_abs_a(TOP_RESULT);a.ret()
