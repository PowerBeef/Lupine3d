"""Accepted-action foreground publication over an immutable world OAM copy.

Bank 4 owns OAM copies and a 16-slot SPSC queue (15 usable entries). Main
simulation produces complete records before HEAD; VBlank consumes at most
two. World commits consume four before waiting and block foreground DMA until
post-commit copying finishes. No VRAM or mask ownership changes in this lane.
"""
from .layout import *


def emit_foreground(a: Assembler):
    if not FOREGROUND_PUBLICATION:return
    a.labels["foreground_serial"]=FG_SERIAL
    a.label("foreground_reset")
    a.xor_r("a");a.ld_abs_a(FG_READY)  # consumer stops before either index is reset
    for address in (FG_HEAD,FG_TAIL,FG_ACTIVE,FG_CHANGED):a.ld_abs_a(address)
    a.ret()

    a.label("foreground_queue_pointer")  # A=index, bank 4 selected; HL=record
    a.ld_r_r("e","a");a.add_a_r("a");a.ld_r_r("l","a");a.add_a_r("a");a.add_a_r("a");a.add_a_r("l")
    a.ld_r_r("l","a");a.ld_r_n("h",FG_QUEUE>>8);a.ret()

    a.label("enqueue_foreground_fire")
    a.ld_a_abs(FG_HEAD);a.inc_r("a");a.and_n(15);a.ld_r_r("b","a");a.ld_a_abs(FG_TAIL);a.cp_r("b");a.jr("foreground_queue_full","z")
    a.ldh_a_n(SVBK);a.push("af");a.ld_r_n("a",4);a.ldh_n_a(SVBK)
    a.ld_rr_nn("hl",FG_SEQUENCE);a.inc_r("(hl)");a.jr("foreground_sequence_ready","nz");a.inc_rr("hl");a.inc_r("(hl)")
    a.label("foreground_sequence_ready")
    a.ld_a_abs(FG_HEAD);a.call("foreground_queue_pointer")
    for address in (FG_SEQUENCE,FG_SEQUENCE+1,SIM_TICK,SIM_TICK+1):a.ld_a_abs(address);a.ldi_hl_a()
    a.label("foreground_read_accepted_clock")
    a.ld_a_abs(SIM_CLOCK+1);a.ld_r_r("b","a");a.ld_a_abs(SIM_CLOCK);a.ld_r_r("e","a")
    a.ld_a_abs(SIM_CLOCK+1);a.cp_r("b");a.jr("foreground_read_accepted_clock","nz")
    a.ld_r_r("a","e");a.ldi_hl_a();a.ld_r_r("a","b");a.ldi_hl_a()
    for address in (WALL_EPOCH,WALL_EPOCH+1):a.ld_a_abs(address);a.ldi_hl_a()
    a.ld_r_n("a",1);a.ldi_hl_a();a.xor_r("a");a.ld_hl_a()
    a.label("foreground_producer_commit")
    a.ld_a_abs(FG_HEAD);a.inc_r("a");a.and_n(15);a.ld_abs_a(FG_HEAD)
    a.pop("af");a.ldh_n_a(SVBK);a.ret()
    a.label("foreground_queue_full")  # pending entries retained; reject new event with explicit overflow count
    a.ld_rr_nn("hl",FG_OVERFLOW);a.inc_r("(hl)");a.ret("nz");a.inc_rr("hl");a.inc_r("(hl)");a.ret()

    a.label("consume_foreground_events")  # bank 4, target generation fixed, max four; no DMA
    a.ld_r_n("a",4);a.ld_abs_a(FG_BUDGET)
    a.label("consume_foreground_events_bounded")
    a.label("foreground_consume_loop")
    a.ld_a_abs(FG_HEAD);a.ld_r_r("b","a");a.ld_a_abs(FG_TAIL);a.cp_r("b");a.ret("z")
    a.call("foreground_queue_pointer");a.push("hl");a.ld_rr_nn("de",6);a.add_hl_rr("de")
    for i in range(2):
        a.ld_a_abs(FG_TARGET_GENERATION+i);a.ld_r_r("b","a");a.ldi_a_hl();a.cp_r("b");a.jr("foreground_generation_mismatch","nz")
    a.ld_a_hl();a.cp_n(1);a.jr("foreground_unknown_event","nz")
    a.pop("hl")
    for address in (FG_CONSUMED_SEQUENCE,FG_CONSUMED_SEQUENCE+1):a.ldi_a_hl();a.ld_abs_a(address)
    a.label("foreground_event_consumed")
    a.ld_r_n("a",9);a.ld_abs_a(FG_ACTIVE);a.ld_r_n("a",1);a.ld_abs_a(FG_CHANGED);a.jr("foreground_advance_tail")
    a.label("foreground_generation_mismatch")
    a.pop("hl");a.ld_rr_nn("de",6);a.add_hl_rr("de")
    for i in range(2):
        a.ld_a_abs(WALL_EPOCH+i);a.ld_r_r("b","a");a.ldi_a_hl();a.cp_r("b");a.jr("foreground_advance_tail","nz")
    a.ret()  # current scene has not yet published: retain its pending event
    a.label("foreground_unknown_event");a.pop("hl")
    a.label("foreground_advance_tail")
    a.ld_a_abs(FG_TAIL);a.inc_r("a");a.and_n(15);a.ld_abs_a(FG_TAIL)
    a.ld_rr_nn("hl",FG_BUDGET);a.dec_r("(hl)");a.jp("foreground_consume_loop","nz");a.ret()

    a.label("prepare_foreground_commit")  # main, before publication waits
    a.ld_r_n("a",1);a.ld_abs_a(FG_WORLD_PENDING)
    for i in range(2):a.ld_a_abs(FG_FRAME_GENERATION+i);a.ld_abs_a(FG_TARGET_GENERATION+i)
    a.ld_r_n("a",4);a.ldh_n_a(SVBK);a.call("consume_foreground_events")
    a.ld_r_n("a",1);a.ldh_n_a(SVBK);a.jp("update_muzzle_oam")

    a.label("finish_foreground_commit")  # after visible commit; copying may extend beyond VBlank
    a.ld_r_n("a",4);a.ldh_n_a(SVBK)
    a.ld_rr_nn("hl",OAM_SHADOW);a.ld_rr_nn("de",FG_PUBLISHED_OAM);a.call("foreground_copy_oam")
    for i in range(2):a.ld_a_abs(FG_FRAME_GENERATION+i);a.ld_abs_a(FG_PUBLISHED_GENERATION+i)
    a.xor_r("a");a.ld_abs_a(FG_CHANGED);a.ld_abs_a(FG_READY)
    for i in range(2):
        a.ld_a_abs(WALL_EPOCH+i);a.ld_r_r("b","a");a.ld_a_abs(FG_PUBLISHED_GENERATION+i);a.cp_r("b");a.jr("foreground_finish_restore","nz")
    a.ld_r_n("a",1);a.ld_abs_a(FG_READY)
    a.label("foreground_finish_restore")
    a.ld_r_n("a",1);a.ldh_n_a(SVBK);a.xor_r("a");a.ld_abs_a(FG_WORLD_PENDING);a.ret()

    a.label("foreground_copy_oam")  # HL->DE exactly160, local registers, ISR-safe (no copy_bc scratch)
    a.ld_r_n("b",10)
    a.label("foreground_copy_loop")
    for _ in range(16):a.ldi_a_hl();a.ld_mem_rr_a("de");a.inc_rr("de")
    a.dec_r("b");a.jr("foreground_copy_loop","nz");a.ret()

    a.label("foreground_vblank")  # called with AF/BC/DE/HL preserved by ISR
    a.ld_a_abs(FG_READY);a.or_r("a");a.ret("z")
    a.ld_a_abs(FG_WORLD_PENDING);a.or_r("a");a.ret("nz")
    # A delayed interrupt must retain the event for the next safe interval.
    # Worst work fits eight lines even when entry is at the end of line 144.
    a.ldh_a_n(LY);a.cp_n(144);a.ret("nz")
    a.ldh_a_n(SVBK);a.push("af");a.ld_r_n("a",4);a.ldh_n_a(SVBK)
    a.ld_a_abs(FG_ACTIVE);a.or_r("a");a.jr("foreground_tick_events","z")
    a.dec_r("a");a.ld_abs_a(FG_ACTIVE);a.jr("foreground_tick_events","nz")
    a.ld_r_n("a",1);a.ld_abs_a(FG_CHANGED)
    a.label("foreground_tick_events")
    for i in range(2):a.ld_a_abs(FG_PUBLISHED_GENERATION+i);a.ld_abs_a(FG_TARGET_GENERATION+i)
    a.ld_r_n("a",2);a.ld_abs_a(FG_BUDGET);a.call("consume_foreground_events_bounded")
    a.ld_a_abs(FG_CHANGED);a.or_r("a");a.jr("foreground_vblank_restore","z")
    a.ld_rr_nn("hl",FG_PUBLISHED_OAM);a.ld_rr_nn("de",FG_COMPOSITE_OAM);a.call("foreground_copy_oam")
    a.ld_a_abs(FG_ACTIVE);a.or_r("a");a.ld_r_n("a",0);a.jr("foreground_composite_y","z");a.ld_r_n("a",72)
    a.label("foreground_composite_y");a.ld_abs_a(FG_COMPOSITE_OAM+9*4)
    # Patch only the source immediate, outside the running HRAM transfer.
    a.ld_r_n("a",FG_COMPOSITE_OAM>>8);a.ldh_n_a((OAM_DMA_HRAM+1)&255);a.call_abs(OAM_DMA_HRAM)
    a.ld_r_n("a",OAM_SHADOW>>8);a.ldh_n_a((OAM_DMA_HRAM+1)&255)
    a.label("foreground_published")
    a.ld_rr_nn("hl",FG_SERIAL);a.inc_r("(hl)");a.xor_r("a");a.ld_abs_a(FG_CHANGED)
    a.label("foreground_vblank_restore");a.pop("af");a.ldh_n_a(SVBK);a.ret()
