#!/usr/bin/env python3
"""LCD-timed walking, turning and door animation on the actual generated ROM."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

import build_rom as br
from lupine3d_v4.wall_cache import WALL_KEY_RANGES
from playtest import apply_diagnostic_camera, read_block, validate_frame, oam_budget
from sm83emu import CGB, parse_symbols

CPU_HZ = 8388608
CASES = ("walking", "turning", "walking_turning", "opening_door")


def run_case(rom, labels, name, frames=144):
    c = CGB(rom,labels); c.run(until_pc=labels["main_loop"])
    c.write8(br.SIM_READY,0)
    if name == "opening_door": apply_diagnostic_camera(c,dict(pose=[1152,3136,192]))
    c.run(until_presentations=1); validate_frame(c)
    for address in (br.INPUT_QUEUE_HEAD,br.INPUT_QUEUE_TAIL,br.INPUT_QUEUE_OVERFLOW,
                    br.SIM_CLOCK,br.SIM_CLOCK+1,br.SIM_TICK,br.SIM_TICK+1): c.write8(address,0)
    c.write8(br.SIM_READY,1)
    start, first_frame = c.cycles, c.frame_count
    def buttons(*_):
        tick = c.frame_count-first_frame
        if name == "opening_door": return 32 if tick == 8 else 0
        if name == "turning": return 1
        if name == "walking_turning": return 5
        return 4 if (tick//48) % 2 == 0 else 8
    c.button_provider = buttons
    def wall_key():
        return b"".join(read_block(c,address,count) for address,_,count in WALL_KEY_RANGES)
    previous_key, previous_count, previous_cycle = wall_key(),c.presentations,c.cycles
    previous_page = c.page_swaps
    rows = []
    while c.frame_count-first_frame < frames:
        c.step()
        if c.presentations == previous_count: continue
        check = validate_frame(c); event = c.commit_events[-1]
        key = wall_key(); reused = bool(c.read8(br.FRAME_REUSED))
        assert reused == (key == previous_key), (name,"wall invalidation",event)
        assert c.page_swaps-previous_page == int(not reused)
        assert event["vblank_safe"] and oam_budget(c)["max_oam_per_scanline"] <= 10
        rows.append(dict(cycles=c.cycles-previous_cycle,lcd_frame=c.frame_count-first_frame,
                         reused=reused,gdma_blocks=event["blocks"],casts=check["executed_casts"],
                         pose=[c.read16(br.PLAYER_XL),c.read16(br.PLAYER_YL),c.read8(br.ANGLE)],
                         door_state=c.read8(br.DOOR_TABLE+4),door_fraction=c.read8(br.DOOR_TABLE+5)))
        previous_key, previous_count, previous_cycle = key,c.presentations,c.cycles
        previous_page = c.page_swaps
    assert c.read8(br.INPUT_QUEUE_OVERFLOW) == 0 and c.gdma_vblank_violations == 0
    assert rows and any(not row["reused"] for row in rows)
    poses = {tuple(row["pose"][:2]) for row in rows}; angles = {row["pose"][2] for row in rows}
    if "walking" in name: assert len(poses)>3, (name,poses)
    if "turning" in name: assert len(angles)>3, (name,angles)
    if name == "opening_door":
        assert rows[-1]["door_state"] == 2
        assert len({row["door_fraction"] for row in rows if row["door_state"] == 1})>=2
    elapsed = (c.cycles-start)/CPU_HZ
    full = [row["cycles"] for row in rows if not row["reused"]]
    return dict(lcd_frame_counter_delta=frames,elapsed_seconds=elapsed,
                presentations=len(rows),full_geometry_updates=len(full),reused_updates=len(rows)-len(full),
                full_geometry_updates_hz=len(full)/elapsed,presentations_hz=len(rows)/elapsed,
                full_mean_cycles=statistics.fmean(full),full_max_cycles=max(full),
                mean_cycles=statistics.fmean(row["cycles"] for row in rows),
                max_cycles=max(row["cycles"] for row in rows),
                unique_positions=len(poses),unique_angles=len(angles),
                wall_invalidation_exact=True,input_queue_overflow=0,unsafe_gdma_starts=0,updates=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-rom",type=Path)
    parser.add_argument("--baseline-symbols",type=Path)
    parser.add_argument("--output",type=Path,default=br.BUILD/"motion_benchmark.json")
    args = parser.parse_args()
    if bool(args.baseline_rom) != bool(args.baseline_symbols): parser.error("Supply both baseline paths")
    rom,a,_ = br.make_rom()
    report = dict(candidate_sha256=hashlib.sha256(rom).hexdigest(),
                  initial_diagnostic_setup=True,game_ram_writes_after_trial_start=0,
                  physical_hardware_tested=False,cases={})
    for name in CASES:
        report["cases"][name] = dict(candidate=run_case(rom,a.labels,name))
    if args.baseline_rom:
        baseline = args.baseline_rom.read_bytes(); labels = parse_symbols(args.baseline_symbols)
        report["baseline_sha256"] = hashlib.sha256(baseline).hexdigest()
        for name in CASES: report["cases"][name]["baseline"] = run_case(baseline,labels,name)
    report["passed"] = True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    summary = {**report,"cases":{name:{lane:{k:v for k,v in data.items() if k!="updates"}
                                               for lane,data in lanes.items()}
                                for name,lanes in report["cases"].items()}}
    print(json.dumps(summary,indent=2))


if __name__ == "__main__": main()
