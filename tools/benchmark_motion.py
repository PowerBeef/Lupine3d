#!/usr/bin/env python3
"""LCD-timed walking, turning and door animation on the actual generated ROM."""
import argparse
import hashlib
import json
import statistics
import math
from pathlib import Path

import build_rom as br
from lupine3d_v4.wall_cache import WALL_KEY_RANGES
from playtest import apply_diagnostic_camera, read_block, validate_frame, oam_budget, set_test_world_byte
from sm83emu import CGB, parse_symbols
from runtime_observer import RuntimeObserver, distribution, LCD_CPU_CYCLES

CPU_HZ = 8388608
CASES = ("walking", "turning", "walking_turning", "opening_door")
EXTENDED_CASES = CASES + ("moving_fire", "open_door", "closed_door", "two_actor_corner")


def input_replay(name, frames):
    """A complete LCD-indexed tape; both ROMs receive identical input."""
    result = []
    for tick in range(frames + 1):
        walk = 4 if (tick // 48) % 2 == 0 else 8
        if name == "opening_door": buttons = 32 if tick == 8 else 0
        elif name == "turning": buttons = 1
        elif name == "walking_turning": buttons = walk | 1
        elif name == "moving_fire": buttons = walk | 1 | (16 if tick % 30 == 8 else 0)
        elif name == "two_actor_corner": buttons = 8 | (1 if tick % 6 == 0 else 0)
        else: buttons = walk
        result.append(buttons)
    return bytes(result)


def run_case(rom, labels, name, frames=144, *, observe=True):
    physical = "refine_full_snapshot" in labels
    c = CGB(rom,labels); c.run(until_pc=labels["main_loop"])
    c.write8(br.SIM_READY,0)
    if name in ("opening_door", "open_door", "closed_door"):
        apply_diagnostic_camera(c,dict(pose=[1152,3136,192]))
    if name == "open_door":
        set_test_world_byte(c, br.DOOR_TABLE + 4, 2)
        set_test_world_byte(c, br.DOOR_TABLE + 5, 255)
    if name == "two_actor_corner":
        # A bounded diagnostic arena lets the controller back around two pursuing
        # actors around a physical corner for a full minute without dying or
        # spending the trial pinned against an authored-room wall.
        grid=bytes(1 if x in (0,15) or y in (0,15) or (x,y)==(8,8) else 0 for y in range(16) for x in range(16))
        for offset,value in enumerate(grid):set_test_world_byte(c,br.MAP+offset,value)
        set_test_world_byte(c,br.DOOR_COUNT,0)
        apply_diagnostic_camera(c, dict(pose=[2944,2176,64]))
        set_test_world_byte(c, br.PLAYER_HEALTH, 255)  # sustained contention, setup only
        set_test_world_byte(c, br.ACTOR_COUNT, 2)
        for index, (x,y) in enumerate(((1920,2176),(2176,1920))):
            values = bytes((x & 255,x >> 8,y&255,y>>8,br.SENTINEL_DORMANT,255)) + bytes(10)
            for offset,value in enumerate(values):
                set_test_world_byte(c, br.ENTITY_SLOTS + index*16 + offset, value)
        for offset,value in enumerate(bytes((128,7,128,8,br.SENTINEL_DORMANT,255))):
            set_test_world_byte(c, br.SENTINEL_XL + offset, value)
    c.run(until_presentations=1); validate_frame(c)
    for address in (br.INPUT_QUEUE_HEAD,br.INPUT_QUEUE_TAIL,br.INPUT_QUEUE_OVERFLOW,
                    br.SIM_CLOCK,br.SIM_CLOCK+1,br.SIM_TICK,br.SIM_TICK+1): c.write8(address,0)
    c.write8(br.SIM_READY,1)
    start, first_frame = c.cycles, c.frame_count
    replay = input_replay(name, frames)
    def buttons(*_):
        tick = c.frame_count-first_frame
        return replay[min(tick, len(replay)-1)]
    c.button_provider = buttons
    observer = RuntimeObserver(c) if observe else None
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
        promoted = physical and bool(c.read8(br.REFINEMENT_DIRTY)) and not c.read8(br.GEOMETRY_BACKBONE_RAN)
        assert reused == (key == previous_key and not promoted), (name,"wall invalidation",event)
        assert c.page_swaps-previous_page == int(not reused)
        assert event["vblank_safe"] and oam_budget(c)["max_oam_per_scanline"] <= 10
        rows.append(dict(cycles=c.cycles-previous_cycle,lcd_frame=c.frame_count-first_frame,
                         reused=reused,refinement_publication=bool(promoted),gdma_blocks=event["blocks"],casts=check["executed_casts"],
                         pose=[c.read16(br.PLAYER_XL),c.read16(br.PLAYER_YL),c.read8(br.ANGLE)],
                         door_state=c.read8(br.DOOR_TABLE+4),door_fraction=c.read8(br.DOOR_TABLE+5),
                         dynamic_tiles=c.read8(br.DYN_COUNT),mask_patterns=c.read8(br.MASK_TILE_COUNT),
                         world_objects=c.read8(br.SENTINEL_OAM_USED),
                         actor_candidates=observer.last_published_actors if observer else None,
                         snapshot_age_ticks=(c.read16(br.SIM_CLOCK)-c.read16(br.FRAME_TICK)) & 65535,
                         input_age_ticks=(c.read16(br.SIM_CLOCK)-c.read16(br.SIM_TICK)) & 65535))
        previous_key, previous_count, previous_cycle = key,c.presentations,c.cycles
        previous_page = c.page_swaps
    assert c.read8(br.INPUT_QUEUE_OVERFLOW) == 0 and c.gdma_vblank_violations == 0
    assert rows and any(not row["reused"] for row in rows)
    poses = {tuple(row["pose"][:2]) for row in rows}; angles = {row["pose"][2] for row in rows}
    moving = name in ("walking", "walking_turning", "moving_fire", "open_door", "closed_door", "two_actor_corner")
    turning = name in ("turning", "walking_turning", "moving_fire", "two_actor_corner")
    if moving: assert len(poses)>3, (name,poses)
    if turning: assert len(angles)>3, (name,angles)
    windows = []
    for first in range(0, frames, 300):
        window = [r for r in rows if first <= r["lcd_frame"] < first+300]
        if len(window) < 3: continue
        positions = len({tuple(r["pose"][:2]) for r in window})
        turns = len({r["pose"][2] for r in window})
        if moving: assert positions > 2, (name,"stationary five-second window",first)
        if turning: assert turns > 2, (name,"nonturning five-second window",first)
        windows.append(dict(start_lcd_frame=first,unique_positions=positions,unique_angles=turns))
    if name == "opening_door":
        assert rows[-1]["door_state"] == 2
        assert len({row["door_fraction"] for row in rows if row["door_state"] == 1})>=2
    if name == "two_actor_corner":
        assert c.wramx[2][br.PLAYER_HEALTH-0xD000]>0, "contention trial ended in player death"
        assert c.wramx[2][br.ACTOR_COUNT-0xD000]==2
        assert all(c.wramx[2][br.ENTITY_SLOTS+i*16+4-0xD000]!=br.SENTINEL_DEAD for i in range(2))
        if observer:
            assert any(len(row["actor_candidates"]) == 2 for row in rows), "both actors must compete in one frame"
        assert sum(row["world_objects"] > 0 for row in rows) >= 3, "contention must reach OAM admission"
    elapsed = (c.cycles-start)/CPU_HZ
    full = [row["cycles"] for row in rows if not row["reused"] and not row["refinement_publication"]]
    observation = observer.report() if observer else None
    if observer:
        assert observation["game_ram_writes_after_trial_start"] == 0
        observer.detach()
    return dict(lcd_frame_counter_delta=frames,elapsed_seconds=elapsed,
                scenario=name,input_replay_sha256=hashlib.sha256(replay).hexdigest(),
                input_replay_encoding="one held-button byte per LCD interval, starting at trial frame zero",
                observation=observation,motion_windows=windows,
                presentations=len(rows),full_geometry_updates=len(full),reused_updates=sum(row["reused"] for row in rows),
                refinement_publications=sum(row["refinement_publication"] for row in rows),
                full_geometry_updates_hz=len(full)/elapsed,presentations_hz=len(rows)/elapsed,
                full_mean_cycles=statistics.fmean(full),full_max_cycles=max(full),
                full_frame_cycles=distribution(full),all_frame_cycles=distribution([r["cycles"] for r in rows]),
                cached_frame_cycles=distribution([r["cycles"] for r in rows if r["reused"]]),
                mean_cycles=statistics.fmean(row["cycles"] for row in rows),
                max_cycles=max(row["cycles"] for row in rows),
                unique_positions=len(poses),unique_angles=len(angles),
                wall_invalidation_exact=True,input_queue_overflow=0,unsafe_gdma_starts=0,updates=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-rom",type=Path)
    parser.add_argument("--baseline-symbols",type=Path)
    parser.add_argument("--candidate-rom",type=Path)
    parser.add_argument("--candidate-symbols",type=Path)
    parser.add_argument("--duration",type=float,help="Emulated seconds per scenario (default: legacy 144 LCD intervals)")
    parser.add_argument("--scenario",action="append",choices=EXTENDED_CASES,help="Repeat to select multiple scenarios")
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--output",type=Path,default=br.BUILD/"motion_benchmark.json")
    args = parser.parse_args()
    if bool(args.baseline_rom) != bool(args.baseline_symbols): parser.error("Supply both baseline paths")
    if bool(args.candidate_rom) != bool(args.candidate_symbols): parser.error("Supply both candidate paths")
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0): parser.error("Duration must be positive and finite")
    frames = max(1,round(args.duration*CPU_HZ/LCD_CPU_CYCLES)) if args.duration is not None else 144
    names = args.scenario or CASES
    rom,a,metadata = br.make_rom()
    labels = a.labels
    if args.candidate_rom:
        rom,labels = args.candidate_rom.read_bytes(),parse_symbols(args.candidate_symbols)
        metadata = {}  # Never assign this process's configuration to an external ROM.
    report = dict(schema="lupine3d.motion.v2",timing_unit="cpu_t_cycles",cpu_hz=CPU_HZ,
                  lcd_cpu_cycles=LCD_CPU_CYCLES,requested_duration_seconds=args.duration,
                  candidate_sha256=hashlib.sha256(rom).hexdigest(),configuration_id=metadata.get("configuration_id"),
                  initial_diagnostic_setup=True,game_ram_writes_after_trial_start=0,
                  physical_hardware_tested=False,cases={})
    for name in names:
        print(f"Measuring candidate {name}: {frames} LCD intervals",flush=True)
        report["cases"][name] = dict(candidate=run_case(rom,labels,name,frames))
    if args.baseline_rom:
        baseline = args.baseline_rom.read_bytes(); labels = parse_symbols(args.baseline_symbols)
        report["baseline_sha256"] = hashlib.sha256(baseline).hexdigest()
        for name in names:
            print(f"Measuring baseline {name}: {frames} LCD intervals",flush=True)
            report["cases"][name]["baseline"] = run_case(baseline,labels,name,frames)
            assert report["cases"][name]["candidate"]["input_replay_sha256"] == report["cases"][name]["baseline"]["input_replay_sha256"]
    report["passed"] = True
    if args.output_dir: args.output = args.output_dir / "motion_benchmark.json"
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    summary = {**report,"cases":{name:{lane:{k:v for k,v in data.items() if k not in ("updates","observation")}
                                               for lane,data in lanes.items()}
                                for name,lanes in report["cases"].items()}}
    print(json.dumps(summary,indent=2))


if __name__ == "__main__": main()
