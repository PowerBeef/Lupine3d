"""Cooperative fixed-tick simulation with bank-isolated render snapshots.

WRAM bank 2 owns the live world. Bank 1 owns a frame snapshot and all render
descriptors. The VBlank ISR only appends timestamped input packets. At ray and
tile-column boundaries the renderer saves its HRAM, services bounded live
simulation work in bank 2, then resumes the untouched bank-1 frame.
"""
from .layout import *  # noqa: F401,F403

# Liveness at the two internal call sites. Registers and per-ray scratch are
# dead there. Bank-1 WRAM is isolated from live queries in bank 2. Public
# render_yield retains the complete historical register/HRAM ABI.
NARROW_CONTEXTS = {
    "ray": ((ADAPTIVE_CASTS, 3), (FRAME_X_POS_L, 8)),
    "column": ((ADAPTIVE_CASTS, 3), (DYN_COUNT, SCAN_STYLE_PTR_H-DYN_COUNT+1),
               (COLUMN_COUNT, COLUMN_MAP_H-COLUMN_COUNT+1), (EDGE_RECASTS, 1), (EVENT_COUNT, 1)),
}


def emit_copy_bulk(a: Assembler) -> None:
    """HL -> DE, BC bytes; four-byte loop halves the counter overhead.

    The ISR never calls this routine. Its fixed remainder byte is therefore
    non-reentrant by design, independent of the selected world WRAM bank.
    """
    a.label("copy_bc")
    a.ld_r_r("a", "c"); a.and_n(3); a.ld_abs_a(COPY_REMAINDER)
    for _ in range(2): a.cb("srl", "b"); a.cb("rr", "c")
    a.ld_r_r("a", "b"); a.or_r("c"); a.jr("copy_bulk_tail", "z")
    a.label("copy_bulk_loop")
    for _ in range(4): a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.dec_rr("bc"); a.ld_r_r("a", "b"); a.or_r("c"); a.jr("copy_bulk_loop", "nz")
    a.label("copy_bulk_tail")
    a.ld_a_abs(COPY_REMAINDER); a.or_r("a"); a.ret("z"); a.ld_r_r("b", "a")
    a.label("copy_bulk_remainder")
    a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de"); a.dec_r("b"); a.jr("copy_bulk_remainder", "nz"); a.ret()


def emit_simulation(a: Assembler) -> None:
    ranges = WORLD_COPY_RANGES
    for name, to_buffer in (("world_to_buffer", True), ("buffer_to_world", False)):
        a.label(name)
        offset = 0
        for world_address, count in ranges:
            source, target = (world_address, WORLD_COPY_BUFFER + offset) if to_buffer else (WORLD_COPY_BUFFER + offset, world_address)
            a.ld_rr_nn("hl", source); a.ld_rr_nn("de", target); a.ld_rr_nn("bc", count); a.call("copy_bc")
            offset += count
        a.ret()

    a.label("init_simulation")
    a.xor_r("a")
    for address in range(SIM_CLOCK, SIM_STEPS + 2):
        a.ld_abs_a(address)
    if FIXED_SIMULATION:
        a.call("world_to_buffer"); a.ld_r_n("a", 2); a.ldh_n_a(SVBK)
        a.call("buffer_to_world"); a.ld_r_n("a", 255); a.ld_abs_a(Q14_RECORD)
        a.ld_r_n("a", 1); a.ldh_n_a(SVBK); a.ld_abs_a(SIM_READY)
    a.ret()

    a.label("begin_frame_snapshot")
    a.call("render_yield")
    a.ld_r_n("a", 2); a.ldh_n_a(SVBK); a.call("world_to_buffer")
    # Flash is a presentation event: acknowledge only after snapshotting it,
    # never expire it unseen while a slow frame is still being rendered.
    a.xor_r("a"); a.ld_abs_a(FLASH)
    a.ld_r_n("a", 1); a.ldh_n_a(SVBK); a.call("buffer_to_world")
    for byte in range(2):
        a.ld_a_abs(SIM_TICK + byte); a.ld_abs_a(FRAME_TICK + byte)
        if FOREGROUND_PUBLICATION:
            a.ld_a_abs(WALL_EPOCH+byte); a.ld_abs_a(FG_FRAME_GENERATION+byte)
    a.ret()

    a.label("queue_vblank_input")
    # ISR owns the producer index and clock. Payload is complete before HEAD
    # changes; the consumer never reads an in-progress slot.
    a.ld_rr_nn("hl", SIM_CLOCK); a.inc_r("(hl)"); a.jr("queue_clock_ready", "nz"); a.inc_rr("hl"); a.inc_r("(hl)")
    a.label("queue_clock_ready")
    a.ld_a_abs(INPUT_QUEUE_HEAD); a.inc_r("a"); a.and_n(63); a.ld_r_r("b", "a")
    a.ld_a_abs(INPUT_QUEUE_TAIL); a.cp_r("b"); a.jr("queue_input_full", "z")
    a.ld_a_abs(INPUT_QUEUE_HEAD); a.add_a_r("a"); a.add_a_r("a"); a.ld_r_r("l", "a"); a.ld_r_n("h", INPUT_QUEUE >> 8)
    for address in (SIM_CLOCK, SIM_CLOCK + 1, INPUT_LAST_RAW, INPUT_EDGE_LATCH):
        a.ld_a_abs(address); a.ldi_hl_a()
    a.xor_r("a"); a.ld_abs_a(INPUT_EDGE_LATCH)
    a.ld_r_r("a", "b"); a.ld_abs_a(INPUT_QUEUE_HEAD); a.ret()
    a.label("queue_input_full")
    # Never silently overwrite a pending press. Saturating diagnostic; the
    # latch also retains at least one pending edge until space is available.
    a.ld_a_abs(INPUT_QUEUE_OVERFLOW); a.cp_n(255); a.ret("z")
    a.inc_r("a"); a.ld_abs_a(INPUT_QUEUE_OVERFLOW); a.ret()

    a.label("render_yield")
    a.push("af")
    a.ld_a_abs(SIM_READY); a.or_r("a"); a.jp("render_yield_idle", "z")
    a.ld_a_abs(INPUT_QUEUE_TAIL)
    # Preserve BC before checking producer state: this is callable between
    # any two ray/column operations, not only at register-dead boundaries.
    a.push("bc"); a.ld_r_r("b", "a"); a.ld_a_abs(INPUT_QUEUE_HEAD); a.cp_r("b")
    a.jr("render_yield_empty", "z")
    a.push("de"); a.push("hl")
    # Leave ISR-owned bytes live; restoring them would lose newly sampled
    # input or rewind the clock when a VBlank occurs during simulation.
    intervals = ((0xFF80, INPUT_LAST_RAW - 0xFF80), (DEPTH_RESULT, HRAM_BYTES_USED - (DEPTH_RESULT - 0xFF80)))
    for source, count in intervals:
        a.ld_rr_nn("hl", source); a.ld_rr_nn("de", RENDER_HRAM_SAVE + source - 0xFF80); a.ld_rr_nn("bc", count); a.call("copy_bc")
    a.ld_r_n("a", 2); a.ldh_n_a(SVBK)
    a.ld_r_n("a", 4); a.ld_abs_a(SIM_BUDGET)
    a.label("service_input_loop")
    a.ld_a_abs(INPUT_QUEUE_TAIL); a.ld_r_r("b", "a"); a.ld_a_abs(INPUT_QUEUE_HEAD); a.cp_r("b"); a.jr("service_input_done", "z")
    a.ld_r_r("a", "b"); a.add_a_r("a"); a.add_a_r("a"); a.ld_r_r("l", "a"); a.ld_r_n("h", INPUT_QUEUE >> 8)
    for address in (SIM_TICK, SIM_TICK + 1, PREV_BUTTONS, PRESSED):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_a_abs(INPUT_QUEUE_TAIL); a.inc_r("a"); a.and_n(63); a.ld_abs_a(INPUT_QUEUE_TAIL)
    a.call("simulation_tick")
    a.ld_rr_nn("hl", SIM_STEPS); a.inc_r("(hl)"); a.jr("simulation_count_ready", "nz"); a.inc_rr("hl"); a.inc_r("(hl)")
    a.label("simulation_count_ready")
    a.ld_a_abs(SIM_BUDGET); a.dec_r("a"); a.ld_abs_a(SIM_BUDGET); a.jr("service_input_loop", "nz")
    a.label("service_input_done")
    a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
    for target, count in intervals:
        a.ld_rr_nn("hl", RENDER_HRAM_SAVE + target - 0xFF80); a.ld_rr_nn("de", target); a.ld_rr_nn("bc", count); a.call("copy_bc")
    a.pop("hl"); a.pop("de")
    a.label("render_yield_empty"); a.pop("bc")
    a.label("render_yield_idle"); a.pop("af"); a.ret()

    if NARROW_YIELDS:
        for name, spans in NARROW_CONTEXTS.items():
            a.label("render_yield_" + name)
            a.ld_a_abs(SIM_READY); a.or_r("a"); a.ret("z")
            a.ld_a_abs(INPUT_QUEUE_TAIL); a.ld_r_r("b", "a")
            a.ld_a_abs(INPUT_QUEUE_HEAD); a.cp_r("b"); a.ret("z")
            for source, count in spans:
                a.ld_rr_nn("hl", source); a.ld_rr_nn("de", RENDER_HRAM_SAVE+source-0xFF80)
                a.ld_rr_nn("bc", count); a.call("copy_bc")
            a.ld_r_n("a", 2); a.ldh_n_a(SVBK); a.call("narrow_service_input")
            a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
            for target, count in spans:
                a.ld_rr_nn("hl", RENDER_HRAM_SAVE+target-0xFF80); a.ld_rr_nn("de", target)
                a.ld_rr_nn("bc", count); a.call("copy_bc")
            a.ret()
        a.label("narrow_service_input")
        a.ld_r_n("a", 4); a.ld_abs_a(SIM_BUDGET)
        a.label("narrow_service_input_loop")
        a.ld_a_abs(INPUT_QUEUE_TAIL); a.ld_r_r("b", "a"); a.ld_a_abs(INPUT_QUEUE_HEAD); a.cp_r("b"); a.ret("z")
        a.ld_r_r("a", "b"); a.add_a_r("a"); a.add_a_r("a"); a.ld_r_r("l", "a"); a.ld_r_n("h", INPUT_QUEUE >> 8)
        for address in (SIM_TICK, SIM_TICK+1, PREV_BUTTONS, PRESSED):
            a.ldi_a_hl(); a.ld_abs_a(address)
        a.ld_a_abs(INPUT_QUEUE_TAIL); a.inc_r("a"); a.and_n(63); a.ld_abs_a(INPUT_QUEUE_TAIL)
        a.call("simulation_tick")
        a.ld_rr_nn("hl", SIM_STEPS); a.inc_r("(hl)"); a.jr("narrow_simulation_count_ready", "nz"); a.inc_rr("hl"); a.inc_r("(hl)")
        a.label("narrow_simulation_count_ready")
        a.ld_a_abs(SIM_BUDGET); a.dec_r("a"); a.ld_abs_a(SIM_BUDGET); a.jr("narrow_service_input_loop", "nz"); a.ret()

    a.label("simulation_tick")
    a.ld_a_abs(LEVEL_COMPLETE); a.or_r("a"); a.jr("simulation_restart", "nz")
    a.ld_a_abs(PLAYER_HEALTH); a.or_r("a"); a.jr("simulation_alive", "nz")
    a.label("simulation_restart")
    if SABLE_ART or COMPACT_DISPLAY: a.call("stop_art_clocks")
    a.ld_a_abs(PRESSED); a.and_n(128); a.ret("z")
    a.call("load_level"); a.ret()
    a.label("simulation_alive")
    a.call("apply_input_actions")
    if SABLE_ART or COMPACT_DISPLAY: a.call("advance_art_clocks")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.ret("z")
    a.call("update_animated_doors"); a.call("update_actors"); a.ret()
