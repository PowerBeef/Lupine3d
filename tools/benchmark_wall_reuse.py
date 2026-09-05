#!/usr/bin/env python3
"""Exact cached/full A/B and LCD-timed combat input-to-publication measurements."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

import build_rom as br
from benchmark_runtime import scenes
from playtest import apply_diagnostic_camera, read_block, set_test_world_byte, validate_frame, oam_budget
from sm83emu import CGB, parse_symbols

CPU_HZ = 8388608


def boot(rom, labels, *, full=False):
    c = CGB(rom, labels); c.run(until_pc=labels["main_loop"])
    c.write8(br.SIM_READY, 0)
    if c.explicit_presentations: c.write8(br.WALL_CACHE_DISABLE, int(full))
    return c


def frame(c):
    c.write8(br.INPUT_QUEUE_TAIL, c.read8(br.INPUT_QUEUE_HEAD))
    before = c.cycles
    c.run(until_presentations=c.presentations+1)
    validate_frame(c)
    assert c.commit_events[-1]["vblank_safe"]
    return c.cycles-before


def packet(c):
    spans = ((br.RAY_TOPS,80),(br.RAY_STYLES,80),(br.RAY_KEYS,80),(br.RAY_ALONG,80),
             (br.RAY_DEPTH,80),(br.RAY_SEGMENT,80),(br.RAY_SURFACE,80),
             (br.PIXEL_TOPS,160),(br.PIXEL_STYLES,160),(br.PIXEL_KEYS,160),
             (br.PIXEL_ALONG,160),(br.PIXEL_SEGMENT,160),(br.PIXEL_SURFACE,160),
             (br.DYNAMIC_TILES,c.read8(br.DYN_COUNT)*16),(br.VIEW_MAP,br.VIEW_MAP_BYTES),
             (br.MASK_TILES,c.read8(br.MASK_TILE_COUNT)*16),(br.HUD_PACKET,br.HUD_PACKET_BYTES))
    data = b"".join(read_block(c,*span) for span in spans)
    # The BG page may differ by design; compare its palette/flip semantics.
    data += bytes(value & ~8 for value in read_block(c,br.VIEW_ATTRIBUTES,br.VIEW_MAP_BYTES))
    data += bytes(c.oam)
    return dict(packet_sha256=hashlib.sha256(data).hexdigest(),
                rgb_sha256=hashlib.sha256(c.render_screen().tobytes()).hexdigest())


def frozen(rom, labels):
    cached, full = boot(rom,labels), boot(rom,labels,full=True)
    rows = []
    for scene in scenes():
        for c in (cached,full):
            c.write8(br.WALL_CACHE_VALID,0)
            apply_diagnostic_camera(c,scene)
            for i in range(len(br.ACTIVE_LEVEL.doors)):
                set_test_world_byte(c,br.DOOR_TABLE+i*6+4,1)
                set_test_world_byte(c,br.DOOR_TABLE+i*6+5,scene["fraction"])
            frame(c)
        cost_cached, cost_full = frame(cached), frame(full)
        assert cached.read8(br.FRAME_REUSED) and not full.read8(br.FRAME_REUSED)
        actual, expected = packet(cached), packet(full)
        assert actual == expected, scene
        assert all(event["destination"] == 0x8000 for event in cached.commit_events[-1]["events"])
        rows.append(dict(scene=scene,full_cycles=cost_full,cached_cycles=cost_cached,
                         cached_gdma_blocks=cached.commit_events[-1]["blocks"],**actual))
    old, new = (statistics.fmean(row[key] for row in rows) for key in ("full_cycles","cached_cycles"))
    return dict(exact_scenes=len(rows),full_mean_cycles=old,cached_mean_cycles=new,
                reduction_percent=(1-new/old)*100,rows=rows)


def live(rom, labels, case, *, full=False):
    c = boot(rom,labels,full=full)
    if case == "combat": apply_diagnostic_camera(c,dict(pose=[2176,2176,0]))
    frame(c)
    # Identical initial world, followed solely by timed controller signals.
    for addr in (br.INPUT_QUEUE_HEAD,br.INPUT_QUEUE_TAIL,br.INPUT_QUEUE_OVERFLOW,
                 br.SIM_CLOCK,br.SIM_CLOCK+1,br.SIM_TICK,br.SIM_TICK+1): c.write8(addr,0)
    c.write8(br.SIM_READY,1)
    start, base_frame = c.cycles, c.frame_count
    pulses = (8,32,56) if case == "combat" else ()
    presses, updates = {}, []
    def keys(*_):
        relative = c.frame_count-base_frame
        return 16 if relative in pulses else (1 if case == "turning" and 8 <= relative < 64 else 0)
    c.button_provider = keys
    last_count, last_cycle, last_anim = c.presentations, c.cycles, None
    anim_changes = 0
    measurement_end = None
    # Preserve the 72-LCD timing window, then allow pending final taps to
    # publish under a bounded, input-free drain. No game-RAM writes occur.
    while c.frame_count-base_frame < 120:
        if c.frame_count-base_frame >= 72:
            if measurement_end is None: measurement_end = c.cycles
            if all('publication_ms' in p for p in presses.values()): break
        relative = c.frame_count-base_frame
        if relative in pulses and relative not in presses:
            presses[relative] = dict(onset_cycle=c.cycles)
        c.step()
        if c.presentations == last_count: continue
        last_count = c.presentations
        validate_frame(c)
        event = c.commit_events[-1]
        assert event["vblank_safe"] and oam_budget(c)["max_oam_per_scanline"] <= 10
        if measurement_end is None:
            updates.append(dict(cycles=c.cycles-last_cycle,reused=event["reused"],blocks=event["blocks"]))
        last_cycle = c.cycles
        if c.read8(br.SENTINEL_VISIBLE) and c.read8(br.SENTINEL_STATE) != br.SENTINEL_DEAD:
            anim = c.read8(br.SENTINEL_ANIM)
            anim_changes += last_anim is not None and anim != last_anim
            last_anim = anim
        if c.oam[9*4]:
            pending = [p for p in presses.values() if "publication_ms" not in p]
            if pending:
                press = pending[0]
                press["publication_ms"] = (event["cycles"]-press["onset_cycle"])*1000/CPU_HZ
                # Earliest LCD scanline containing this muzzle sprite, not a
                # claim about original-LCD response time or human perception.
                row = c.oam[9*4]-16
                scan_cycle = c.cycles+((154-c.ly)*456-c.ppu_dots+row*456)*2
                press["muzzle_scanline_ms"] = (scan_cycle-press["onset_cycle"])*1000/CPU_HZ
    assert len(presses) == len(pulses) and all("publication_ms" in p for p in presses.values()), (case,presses)
    assert c.read8(br.INPUT_QUEUE_OVERFLOW) == 0
    elapsed = (measurement_end-start)/CPU_HZ
    return dict(lcd_frames=72,feedback_drain_lcd_frames=max(0,c.frame_count-base_frame-72),elapsed_seconds=elapsed,presentations=len(updates),
                display_updates_hz=len(updates)/elapsed,
                full_updates=sum(not u["reused"] for u in updates),
                reused_updates=sum(u["reused"] for u in updates),
                mean_cycles=statistics.fmean(u["cycles"] for u in updates),
                max_cycles=max(u["cycles"] for u in updates),
                mean_gdma_blocks=statistics.fmean(u["blocks"] for u in updates),
                visible_enemy_animation_changes=anim_changes,
                presses=list(presses.values()),health=c.read8(br.PLAYER_HEALTH),
                input_queue_overflow=c.read8(br.INPUT_QUEUE_OVERFLOW))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-rom",type=Path)
    parser.add_argument("--baseline-symbols",type=Path)
    parser.add_argument("--output",type=Path,default=br.BUILD/"wall_reuse.json")
    args = parser.parse_args()
    if bool(args.baseline_rom) != bool(args.baseline_symbols):
        parser.error("--baseline-rom and --baseline-symbols must be supplied together")
    rom, asm, _ = br.make_rom()
    report = dict(candidate_sha256=hashlib.sha256(rom).hexdigest(),
                  diagnostic_initial_state_injection=True,physical_hardware_tested=False,
                  frozen=frozen(rom,asm.labels),live={})
    if args.baseline_rom:
        baseline, old_labels = args.baseline_rom.read_bytes(), parse_symbols(args.baseline_symbols)
        report["baseline_sha256"] = hashlib.sha256(baseline).hexdigest()
    for name in ("idle","combat","turning"):
        report["live"][name] = dict(forced_full=live(rom,asm.labels,name,full=True),
                                   cached=live(rom,asm.labels,name))
        if args.baseline_rom: report["live"][name]["beta3"] = live(baseline,old_labels,name)
    report["passed"] = True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({**report,"frozen":{k:v for k,v in report["frozen"].items() if k!="rows"}},indent=2))


if __name__ == "__main__": main()
