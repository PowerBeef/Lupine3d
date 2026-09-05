"""Certified coarse traversal with a Q14 restart at uncertain crossings.

This module deliberately does not change the Q5 projection lookup. The
certificate concerns surface selection, not continuous projection accuracy.
"""
from __future__ import annotations

from .layout import *  # noqa: F401,F403


@lru_cache(maxsize=None)
def q14_direction(angle: int, record: int) -> tuple[int, int]:
    if record < 80:
        screen_x = record * 2 + 1
    elif record < 240:
        screen_x = record - 80 + .5
    elif record == 240:
        screen_x = 80
    else:
        return 0, 0
    theta = angle * math.tau / 256
    offset = math.atan((screen_x - 80) / (80 / math.tan(math.radians(FOV_DEGREES / 2))))
    return round(math.cos(theta + offset) * 16384), round(math.sin(theta + offset) * 16384)


@lru_cache(maxsize=1)
def make_q14_directions() -> bytes:
    return b"".join(component.to_bytes(2, "little", signed=True)
                    for angle in range(256) for record in range(256)
                    for component in q14_direction(angle, record))


def emit_precision(a: Assembler) -> None:
    a.label("q14_crossing_uncertain")
    # |coarse component - Q14 component * 127/16384| < 1 is
    # exhaustively checked at build/test time for every supported ray.
    # Therefore |coarse error| > nextX + nextY certifies its sign.
    a.ld_a_abs(Q14_RECORD); a.cp_n(255); a.jr("q14_certain", "z")
    a.ld_a_abs(DDA_ABS_X); a.or_r("a"); a.jr("q14_uncertain", "z")
    a.ld_a_abs(DDA_ABS_Y); a.or_r("a"); a.jr("q14_uncertain", "z")
    load_hl_abs(a, DDA_ERR_L, DDA_ERR_H)
    a.cb("bit", "h", 7); a.jr("q14_error_positive", "z")
    a.ld_r_r("a", "l"); a.cpl(); a.ld_r_r("l", "a")
    a.ld_r_r("a", "h"); a.cpl(); a.ld_r_r("h", "a"); a.inc_rr("hl")
    a.label("q14_error_positive")
    a.ld_a_abs(DDA_NEXT_X_L); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_NEXT_Y_L); a.add_a_r("b"); a.ld_r_r("e", "a")
    a.ld_a_abs(DDA_NEXT_X_H); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_NEXT_Y_H); a.adc_a_r("b"); a.ld_r_r("d", "a")
    a.ld_r_r("a", "e"); a.sub_r("l")
    a.ld_r_r("a", "d"); a.sbc_a_r("h"); a.jr("q14_certain", "c")
    a.label("q14_uncertain"); a.ld_r_n("a", 1); a.or_r("a"); a.ret()
    a.label("q14_certain"); a.xor_r("a"); a.ret()

    a.label("q14_restart")
    a.ld_a_abs(Q14_FALLBACKS); a.inc_r("a"); a.ld_abs_a(Q14_FALLBACKS)
    a.ld_a_abs(ANGLE); a.cb("swap", "a"); a.and_n(15); a.add_a_n(Q14_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_a_abs(Q14_RECORD); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    a.add_hl_rr("hl"); a.add_hl_rr("hl")
    a.ld_a_abs(ANGLE); a.and_n(15); a.add_a_r("a"); a.add_a_r("a"); a.add_a_n(0x40); a.add_a_r("h"); a.ld_r_r("h", "a")
    for address in (Q14_X, Q14_X + 1, Q14_Y, Q14_Y + 1):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.label("q14_vector_cast")  # signed X/Y vector, origin = current player
    a.ld_r_n("a", 1); a.ld_abs_a(Q14_ACTIVE); a.ld_abs_a(Q14_LOADED)
    for name, component, step, next_low, next_high, pos_low, pos_high, neg_low, neg_high in (
        ("x", Q14_X, DDA_STEP_X, DDA_NEXT_X_L, DDA_NEXT_X_H, FRAME_X_POS_L, FRAME_X_POS_H, FRAME_X_NEG_L, FRAME_X_NEG_H),
        ("y", Q14_Y, DDA_STEP_Y, DDA_NEXT_Y_L, DDA_NEXT_Y_H, FRAME_Y_POS_L, FRAME_Y_POS_H, FRAME_Y_NEG_L, FRAME_Y_NEG_H),
    ):
        load_hl_abs(a, component, component + 1)
        a.cb("bit", "h", 7); a.jr(f"q14_{name}_positive", "z")
        a.call("negate_hl"); store_hl_abs(a, component, component + 1)
        a.ld_r_n("a", 255); a.ld_abs_a(step)
        a.ld_a_abs(neg_low); a.ld_abs_a(next_low); a.ld_a_abs(neg_high); a.ld_abs_a(next_high)
        a.jr(f"q14_{name}_ready")
        a.label(f"q14_{name}_positive")
        a.ld_r_n("a", 1); a.ld_abs_a(step)
        a.ld_a_abs(pos_low); a.ld_abs_a(next_low); a.ld_a_abs(pos_high); a.ld_abs_a(next_high)
        a.label(f"q14_{name}_ready")
    a.ld_a_abs(PLAYER_XH); a.ld_abs_a(DDA_MAP_X)
    a.ld_a_abs(PLAYER_YH); a.ld_abs_a(DDA_MAP_Y)
    a.xor_r("a"); a.ld_abs_a(DDA_CROSSINGS)
    for name, distance, component in (("x", DDA_NEXT_X_L, Q14_Y), ("y", DDA_NEXT_Y_L, Q14_X)):
        load_hl_abs(a, distance, distance + 1)
        a.ld_a_abs(component); a.ld_r_r("e", "a"); a.ld_a_abs(component + 1); a.ld_r_r("d", "a")
        a.call("q14_multiply_u16")
        for byte in range(4):
            if name == "x":
                a.ld_a_abs(Q14_PRODUCT + byte)
            else:
                a.ld_a_abs(Q14_PRODUCT + byte); a.ld_r_r("b", "a")
                a.ld_a_abs(Q14_ERROR + byte)
                (a.sub_r if byte == 0 else a.sbc_a_r)("b")
            a.ld_abs_a(Q14_ERROR + byte)
    # A player already inside an open aperture can still look at the panel
    # remaining in the same cell. Test that local segment before stepping.
    a.call("dda_read_cell"); a.cp_n(3); a.jr("q14_loop", "nz")
    a.call("door_ray_hit"); a.or_r("a"); a.jp("dda_hit", "nz")
    a.label("q14_loop")
    a.ld_a_abs(Q14_X); a.ld_r_r("b", "a"); a.ld_a_abs(Q14_X + 1); a.or_r("b"); a.jp("q14_step_y", "z")
    a.ld_a_abs(Q14_Y); a.ld_r_r("b", "a"); a.ld_a_abs(Q14_Y + 1); a.or_r("b"); a.jp("q14_step_x", "z")
    a.ld_a_abs(Q14_ERROR + 3); a.cb("bit", "a", 7); a.jp("q14_step_x", "nz")
    a.ld_r_r("b", "a")
    for byte in range(3):
        a.ld_a_abs(Q14_ERROR + byte); a.or_r("b"); a.ld_r_r("b", "a")
    a.jp("q14_step_y", "nz")
    for name, axis, step, cell, distance, component in (
        ("x", 0, DDA_STEP_X, DDA_MAP_X, DDA_NEXT_X_L, Q14_Y),
        ("y", 1, DDA_STEP_Y, DDA_MAP_Y, DDA_NEXT_Y_L, Q14_X),
    ):
        a.label(f"q14_step_{name}")
        a.ld_a_abs(step); a.ld_r_r("b", "a"); a.ld_a_abs(cell); a.add_a_r("b"); a.ld_abs_a(cell)
        a.ld_r_n("a", axis); a.ld_abs_a(DDA_AXIS)
        a.ld_a_abs(distance); a.ld_abs_a(DDA_DIST_L); a.ld_a_abs(distance + 1); a.ld_abs_a(DDA_DIST_H)
        a.call("dda_post_step"); a.ret("nz")
        a.ld_a_abs(distance + 1); a.inc_r("a"); a.ld_abs_a(distance + 1)
        # error +/- component * 256; low byte is unchanged.
        for byte in range(1, 4):
            if byte < 3:
                a.ld_a_abs(component + byte - 1); a.ld_r_r("b", "a")
            else:
                a.ld_r_n("b", 0)
            a.ld_a_abs(Q14_ERROR + byte)
            op = (a.add_a_r if byte == 1 else a.adc_a_r) if axis == 0 else (a.sub_r if byte == 1 else a.sbc_a_r)
            op("b"); a.ld_abs_a(Q14_ERROR + byte)
        a.jp("q14_loop")

    a.label("q14_load_door_components")
    # The coarse crossing certificate already establishes which cell was
    # entered. A local panel needs fine components, not a full ray restart.
    a.ld_a_abs(Q14_LOADED); a.or_r("a"); a.ret("nz")
    a.ld_a_abs(ANGLE); a.cb("swap", "a"); a.and_n(15); a.add_a_n(Q14_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_a_abs(Q14_RECORD); a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.add_hl_rr("hl"); a.add_hl_rr("hl")
    a.ld_a_abs(ANGLE); a.and_n(15); a.add_a_r("a"); a.add_a_r("a"); a.add_a_n(0x40); a.add_a_r("h"); a.ld_r_r("h", "a")
    for address in (Q14_X, Q14_X + 1, Q14_Y, Q14_Y + 1):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000); a.ld_abs_a(Q14_LOADED)
    for name, component in (("x", Q14_X), ("y", Q14_Y)):
        load_hl_abs(a, component, component + 1); a.cb("bit", "h", 7); a.jr(f"door_component_{name}_ready", "z")
        a.call("negate_hl"); store_hl_abs(a, component, component + 1)
        a.label(f"door_component_{name}_ready")
    a.ret()

    a.label("q14_multiply_u16")  # HL * DE -> 32-bit product, no overflow
    store_hl_abs(a, Q14_MULTIPLICAND, Q14_MULTIPLICAND + 1)
    a.ld_r_r("a", "e"); a.ld_abs_a(Q14_MULTIPLIER)
    a.ld_r_r("a", "d"); a.ld_abs_a(Q14_MULTIPLIER + 1)
    a.xor_r("a")
    for byte in range(4): a.ld_abs_a(Q14_PRODUCT + byte)
    for left in range(2):
        for right in range(2):
            skip = f"wide_product_{left}_{right}_skip"
            a.ld_a_abs(Q14_MULTIPLICAND + left); a.or_r("a"); a.jr(skip, "z"); a.ld_r_r("b", "a")
            a.ld_a_abs(Q14_MULTIPLIER + right); a.or_r("a"); a.jr(skip, "z"); a.ld_r_r("c", "a")
            a.call("mul_u8")
            start = left + right
            a.ld_a_abs(Q14_PRODUCT + start); a.add_a_r("l"); a.ld_abs_a(Q14_PRODUCT + start)
            a.ld_a_abs(Q14_PRODUCT + start + 1); a.adc_a_r("h"); a.ld_abs_a(Q14_PRODUCT + start + 1)
            for byte in range(start + 2, 4):
                a.ld_a_abs(Q14_PRODUCT + byte); a.adc_a_n(0); a.ld_abs_a(Q14_PRODUCT + byte)
            a.label(skip)
    a.ret()
    a.label("q14_multiply_u16_shift_reference")
    store_hl_abs(a, Q14_MULTIPLICAND, Q14_MULTIPLICAND + 1)
    a.ld_r_r("a", "e"); a.ld_abs_a(Q14_MULTIPLIER)
    a.ld_r_r("a", "d"); a.ld_abs_a(Q14_MULTIPLIER + 1)
    a.xor_r("a")
    for address in (*range(Q14_PRODUCT, Q14_PRODUCT + 4), Q14_MULTIPLICAND + 2, Q14_MULTIPLICAND + 3):
        a.ld_abs_a(address)
    a.ld_r_n("c", 16)
    a.label("q14_multiply_loop")
    a.ld_rr_nn("hl", Q14_MULTIPLIER + 1); a.cb("srl", "(hl)"); a.dec_rr("hl"); a.cb("rr", "(hl)")
    a.jr("q14_multiply_shift", "nc")
    for byte in range(4):
        a.ld_a_abs(Q14_MULTIPLICAND + byte); a.ld_r_r("b", "a")
        a.ld_a_abs(Q14_PRODUCT + byte)
        (a.add_a_r if byte == 0 else a.adc_a_r)("b"); a.ld_abs_a(Q14_PRODUCT + byte)
    a.label("q14_multiply_shift")
    a.ld_rr_nn("hl", Q14_MULTIPLICAND); a.cb("sla", "(hl)")
    for _ in range(3):
        a.inc_rr("hl"); a.cb("rl", "(hl)")
    a.dec_r("c"); a.jp("q14_multiply_loop", "nz"); a.ret()

    a.label("divide_u32_u16")  # Q14_PRODUCT / DE; quotient in Q14_PRODUCT
    # Restoring division. The 17th remainder bit is the carry from ADC HL.
    a.ld_rr_nn("hl", 0); a.ld_r_n("c", 32)
    a.label("divide32_loop")
    for byte in range(4):
        a.ld_a_abs(Q14_PRODUCT + byte)
        if byte == 0:
            a.add_a_r("a")
        else:
            a.rla()
        a.ld_abs_a(Q14_PRODUCT + byte)
    a.ld_r_r("a", "l"); a.rla(); a.ld_r_r("l", "a")
    a.ld_r_r("a", "h"); a.rla(); a.ld_r_r("h", "a"); a.jr("divide32_subtract", "c")
    a.ld_r_r("a", "h"); a.cp_r("d"); a.jr("divide32_next", "c"); a.jr("divide32_subtract", "nz")
    a.ld_r_r("a", "l"); a.cp_r("e"); a.jr("divide32_next", "c")
    a.label("divide32_subtract")
    a.ld_r_r("a", "l"); a.sub_r("e"); a.ld_r_r("l", "a")
    a.ld_r_r("a", "h"); a.sbc_a_r("d"); a.ld_r_r("h", "a")
    a.ld_a_abs(Q14_PRODUCT); a.or_n(1); a.ld_abs_a(Q14_PRODUCT)
    a.label("divide32_next"); a.dec_r("c"); a.jp("divide32_loop", "nz"); a.ret()

    a.label("divide_u32_u16_bounded")
    # Door coordinates need at most a 16-bit quotient. Preload the high-word
    # remainder and perform only sixteen restoring steps; reject overflow.
    load_hl_abs(a, Q14_PRODUCT + 2, Q14_PRODUCT + 3)
    a.ld_r_r("a", "l"); a.sub_r("e"); a.ld_r_r("a", "h"); a.sbc_a_r("d"); a.ret("nc")
    a.xor_r("a"); a.ld_abs_a(Q14_PRODUCT + 2); a.ld_abs_a(Q14_PRODUCT + 3)
    a.ld_r_n("c", 16)
    a.label("divide16_loop")
    a.ld_a_abs(Q14_PRODUCT); a.add_a_r("a"); a.ld_abs_a(Q14_PRODUCT)
    a.ld_a_abs(Q14_PRODUCT + 1); a.rla(); a.ld_abs_a(Q14_PRODUCT + 1)
    a.ld_r_r("a", "l"); a.rla(); a.ld_r_r("l", "a"); a.ld_r_r("a", "h"); a.rla(); a.ld_r_r("h", "a"); a.jr("divide16_subtract", "c")
    a.ld_r_r("a", "h"); a.cp_r("d"); a.jr("divide16_next", "c"); a.jr("divide16_subtract", "nz")
    a.ld_r_r("a", "l"); a.cp_r("e"); a.jr("divide16_next", "c")
    a.label("divide16_subtract")
    a.ld_r_r("a", "l"); a.sub_r("e"); a.ld_r_r("l", "a"); a.ld_r_r("a", "h"); a.sbc_a_r("d"); a.ld_r_r("h", "a")
    a.ld_a_abs(Q14_PRODUCT); a.or_n(1); a.ld_abs_a(Q14_PRODUCT)
    a.label("divide16_next"); a.dec_r("c"); a.jp("divide16_loop", "nz"); a.ret()
