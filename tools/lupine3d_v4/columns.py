"""Streaming physical-column construction; geometry and rounding stay exact."""
from .layout import *


def emit_column_expansion(a: Assembler):
    # HL walks pair tops, DE walks physical tops. B/C retain previous/current
    # samples, avoiding repeated index arithmetic and scratch-memory loads.
    a.ld_rr_nn("hl", RAY_TOPS); a.ld_rr_nn("de", PIXEL_TOPS)
    a.ldi_a_hl(); a.ld_r_r("b", "a"); a.ld_r_r("c", "a")
    a.label("pixel_pair_loop")
    a.ld_r_r("a", "c"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r("b")
    a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a")
    a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ld_r_r("a", "c"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r("(hl)")
    a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a")
    a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ld_r_r("b", "c"); a.ldi_a_hl(); a.ld_r_r("c", "a")
    a.ld_r_r("a", "l"); a.cp_n((RAY_TOPS + RAYS) & 255); a.jr("pixel_pair_loop", "nz")
    # Last pair clamps its following sample to itself; retain even the old
    # byte-arithmetic rounding contract for synthetic descriptor probes.
    for neighbour in ("b", "c"):
        a.ld_r_r("a", "c"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r(neighbour)
        a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a")
        a.ld_mem_rr_a("de"); a.inc_rr("de")
    for source, destination in ((RAY_STYLES, PIXEL_STYLES), (RAY_KEYS, PIXEL_KEYS),
                                (RAY_ALONG, PIXEL_ALONG), (RAY_SEGMENT, PIXEL_SEGMENT),
                                (RAY_SURFACE, PIXEL_SURFACE)):
        a.ld_rr_nn("hl", source); a.ld_rr_nn("de", destination)
        a.call("duplicate_pair_stream")
    a.ld_r_n("a", RAYS); a.ld_abs_a(PAIR_INDEX)
    a.jp("pixel_expansion_done")
    a.label("duplicate_pair_stream")
    a.ld_r_n("b", RAYS // 4)
    a.label("duplicate_pair_group")
    for _ in range(4):
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
        a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.dec_r("b"); a.jr("duplicate_pair_group", "nz"); a.ret()
    a.label("pixel_expansion_done")


def column_pointer(a: Assembler, base: int):
    """HL = base + E (physical column 0..159); preserve B/C/D/E."""
    if base & 255:
        a.ld_r_r("a", "e"); a.add_a_n(base & 255); a.ld_r_r("l", "a")
        if (base & 255) + PHYSICAL_COLUMNS - 1 > 255:
            a.ld_r_n("a", base >> 8); a.adc_a_n(0); a.ld_r_r("h", "a")
        else:
            a.ld_r_n("h", base >> 8)
    else:
        a.ld_r_n("h", base >> 8); a.ld_r_r("l", "e")


def emit_surface_scan(a: Assembler):
    # B/C/D carry previous segment/key/along; E is the current column.
    # Every branch refreshes all three values, including after a hard edge.
    a.xor_r("a"); a.ld_abs_a(EVENT_COUNT)
    for address, register in ((PIXEL_SEGMENT, "b"), (PIXEL_KEYS, "c"), (PIXEL_ALONG, "d")):
        a.ld_a_abs(address); a.ld_r_r(register, "a")
    a.ld_r_n("e", 1)
    a.label("event_boundary_loop")
    column_pointer(a, PIXEL_SEGMENT)
    a.ld_a_hl(); a.cp_r("b"); a.ld_r_r("b", "a"); a.jr("event_physical_break", "nz")
    column_pointer(a, PIXEL_KEYS)
    a.ld_a_hl(); a.cp_r("c"); a.ld_r_r("c", "a"); a.jr("event_material_change", "nz")
    column_pointer(a, PIXEL_ALONG)
    a.ld_a_hl(); a.cp_r("d"); a.ld_r_r("d", "a"); a.jr("event_boundary_done", "z")
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT); a.jr("event_boundary_done")
    a.label("event_physical_break")
    column_pointer(a, PIXEL_TOPS)
    a.ld_a_hl(); a.cp_n(41); a.jr("event_physical_lod_skip", "nc")
    column_pointer(a, PIXEL_STYLES)
    a.ld_hl_n(CREASE_STYLE)
    a.label("event_physical_lod_skip")
    column_pointer(a, PIXEL_KEYS)
    a.ld_a_hl(); a.ld_r_r("c", "a")
    a.label("event_material_change")
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT)
    column_pointer(a, PIXEL_ALONG)
    a.ld_a_hl(); a.ld_r_r("d", "a")
    a.label("event_boundary_done")
    a.inc_r("e"); a.ld_r_r("a", "e"); a.cp_n(PHYSICAL_COLUMNS)
    a.jp("event_boundary_loop", "c")

    # Door runs scan the key stream once. Their stencil is applied after all
    # physical-edge decisions, retaining the original overwrite precedence.
    a.ld_rr_nn("hl", PIXEL_KEYS); a.ld_r_n("b", 0)
    a.label("door_scan_loop")
    a.ld_r_r("a", "b"); a.cp_n(PHYSICAL_COLUMNS); a.jp("door_scan_done", "nc")
    a.ldi_a_hl(); a.and_n(0x60); a.cp_n(0x60); a.jp("door_scan_advance", "nz")
    a.ld_r_r("a", "b"); a.ld_abs_a(DOOR_RUN_START)
    a.label("door_find_end")
    a.inc_r("b"); a.ld_r_r("a", "b"); a.cp_n(PHYSICAL_COLUMNS); a.jr("door_end_ready", "z")
    if DOOR_IDENTITY:
        a.push("hl")
        for number,base in enumerate((PIXEL_KEYS,PIXEL_SEGMENT,PIXEL_ALONG)):
            a.ld_a_abs(DOOR_RUN_START); a.ld_r_r("e","a"); column_pointer(a,base); a.ld_a_hl(); a.ld_r_r("c","a")
            a.ld_r_r("e","b"); column_pointer(a,base); a.ld_a_hl(); a.cp_r("c"); a.jr("door_identity_end","nz")
        a.pop("hl"); a.inc_rr("hl"); a.jr("door_find_end")
        a.label("door_identity_end"); a.pop("hl")
    else:
        a.ldi_a_hl(); a.and_n(0x60); a.cp_n(0x60); a.jr("door_find_end", "z")
        a.dec_rr("hl")  # first non-door cell will be consumed by the outer scan
    a.label("door_end_ready")
    a.ld_r_r("a", "b"); a.ld_abs_a(DOOR_RUN_END)
    a.push("bc"); a.push("hl")


def emit_surface_scan_end(a: Assembler):
    a.label("door_event_count")
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT)
    a.pop("hl"); a.pop("bc"); a.jp("door_scan_loop")
    a.label("door_scan_advance"); a.inc_r("b"); a.jp("door_scan_loop")
    a.label("door_scan_done"); a.ld_abs_a(EVENT_INDEX); a.ret()
