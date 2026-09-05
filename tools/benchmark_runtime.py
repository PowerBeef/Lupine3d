#!/usr/bin/env python3
"""Compare exact frozen-world outputs and cycles against an archived ROM.

Live routes remain separate: faster rendering changes the simulation tick at
which a visual update is sampled. This diagnostic freezes simulation, retains
LCD interrupts/publication, and compares the actual generated programs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

import build_rom as br
from playtest import apply_diagnostic_camera, read_block, set_test_world_byte, validate_frame
from sm83emu import CGB, parse_symbols


def scenes():
    result = []
    for name in ("coherence_tour", "sable_art_tour"):
        for action in json.loads((br.ROOT / "playtests" / (name + ".json")).read_text())["actions"]:
            if "pose" in action:
                result.append(dict(name=name + ":" + action.get("capture", str(len(result))),
                                   pose=action["pose"], fraction=0))
    for door in br.ACTIVE_LEVEL.doors:
        for side in (-1, 1):
            pose = ([door.x * 256 + 128 + side * 448, door.y * 256 + 128, 0 if side < 0 else 128]
                    if door.orientation == 0 else
                    [door.x * 256 + 128, door.y * 256 + 128 + side * 448, 64 if side < 0 else 192])
            for fraction in (0, 64, 128, 192, 224):
                result.append(dict(name=f"{door.name}:{side}:{fraction}", pose=pose, fraction=fraction))
    return result


def measure(rom, labels, scene):
    c = CGB(rom, labels)
    c.run(until_pc=labels["main_loop"])
    c.write8(br.SIM_READY, 0)
    apply_diagnostic_camera(c, scene)
    for i in range(len(br.ACTIVE_LEVEL.doors)):
        set_test_world_byte(c, br.DOOR_TABLE + i * br.DOOR_RECORD_BYTES + 4, 1)
        set_test_world_byte(c, br.DOOR_TABLE + i * br.DOOR_RECORD_BYTES + 5, scene["fraction"])
    start = c.cycles
    c.run(until_pc=labels["cast_all"])
    cast_start = c.cycles
    c.run(until_pc=labels["build_pixel_descriptors"])
    expansion_start = c.cycles
    c.run(until_pc=labels["edge_recast_loop"])
    expansion_cycles = c.cycles - expansion_start
    c.run(until_pc=labels["decorate_pixel_styles"])
    events_start = c.cycles
    c.run(until_pc=labels["render_view"])
    cast_cycles = c.cycles - cast_start
    event_cycles = c.cycles - events_start
    c.run(until_presentations=1)
    validate_frame(c)
    groups = {
        "pairs": [(br.RAY_TOPS, 80), (br.RAY_STYLES, 80), (br.RAY_KEYS, 80),
                  (br.RAY_ALONG, 80), (br.RAY_DEPTH, 80), (br.RAY_SEGMENT, 80),
                  (br.RAY_SURFACE, 80)],
        "physical": [(br.PIXEL_TOPS, 160), (br.PIXEL_STYLES, 160), (br.PIXEL_KEYS, 160),
                     (br.PIXEL_ALONG, 160), (br.PIXEL_SEGMENT, 160), (br.PIXEL_SURFACE, 160)],
        "background": [(br.DYNAMIC_TILES, c.read8(br.DYN_COUNT) * 16), (br.VIEW_MAP, 384),
                       (br.VIEW_ATTRIBUTES, 384)],
        "objects": [(br.OAM_SHADOW, 160), (br.MASK_TILES, c.read8(br.MASK_TILE_COUNT) * 16)],
        "hud": [(br.HUD_PACKET, 11)],
    }
    hashes = {}
    for name, spans in groups.items():
        data = bytearray(b"".join(read_block(c, address, count) for address, count in spans))
        if name == "objects":
            # Independent OBJ ownership may leave a different stale bank bit
            # in a Y=0 (disabled) slot. All visible OAM and all other bytes stay
            # exact; do not normalize palette, tile, X, or enabled objects.
            for offset in range(0, 160, 4):
                if data[offset] == 0: data[offset+3] &= ~8
        hashes[name] = hashlib.sha256(data).hexdigest()
    hashes["rgb"] = hashlib.sha256(c.render_screen().tobytes()).hexdigest()
    return dict(hashes=hashes, cycles=c.cycles - start, cast_cycles=cast_cycles,
                column_expansion_cycles=expansion_cycles, surface_event_cycles=event_cycles,
                dynamic_tiles=c.read8(br.DYN_COUNT),
                casts=c.read8(br.ADAPTIVE_CASTS)+c.read8(br.EDGE_RECASTS),
                material_events=c.read8(br.EVENT_COUNT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-rom", type=Path, required=True)
    parser.add_argument("--baseline-symbols", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path, help="Reuse hash- and scene-bound frozen measurements")
    parser.add_argument("--output", type=Path, default=br.BUILD / "runtime_comparison.json")
    args = parser.parse_args()
    baseline = args.baseline_rom.read_bytes()
    labels = parse_symbols(args.baseline_symbols)
    candidate, asm, manifest = br.make_rom()
    recorded = None
    if args.baseline_report:
        evidence = json.loads(args.baseline_report.read_text())
        if not evidence["passed"] or not evidence["simulation_frozen"]:
            raise ValueError("Baseline report is not a passing frozen comparison")
        lane = "candidate" if evidence["candidate_sha256"] == hashlib.sha256(baseline).hexdigest() else "baseline"
        if evidence[lane+"_sha256"] != hashlib.sha256(baseline).hexdigest():
            raise ValueError("Baseline report hash does not match baseline ROM")
        if [row["scene"] for row in evidence["scenes"]] != scenes():
            raise ValueError("Baseline report scene definitions have changed")
        recorded = {row["scene"]["name"]:row[lane] for row in evidence["scenes"]}
    rows = []
    for scene in scenes():
        before = recorded[scene["name"]] if recorded is not None else measure(baseline, labels, scene)
        after = measure(candidate, asm.labels, scene)
        if any(before[key] != after[key] for key in ("hashes", "casts", "material_events")):
            raise AssertionError((scene, before, after))
        rows.append(dict(scene=scene, baseline=before, candidate=after))
    report = dict(schema="lupine3d.frozen.v2",timing_unit="cpu_t_cycles",cpu_hz=8388608,
                  configuration_id=manifest["configuration_id"],
                  baseline_report_sha256=hashlib.sha256(args.baseline_report.read_bytes()).hexdigest() if args.baseline_report else None,
                  passed=True, simulation_frozen=True, diagnostic_ram_injections=True,
                  baseline_sha256=hashlib.sha256(baseline).hexdigest(),
                  candidate_sha256=hashlib.sha256(candidate).hexdigest(), scene_count=len(rows),
                  normalization="Only OBJ bank bit 3 in disabled Y=0 OAM slots",
                  exact_groups=list(rows[0]["candidate"]["hashes"]), scenes=rows)
    for key in ("cycles", "cast_cycles", "column_expansion_cycles", "surface_event_cycles"):
        old, new = (statistics.fmean(row[version][key] for row in rows) for version in ("baseline", "candidate"))
        report[key] = dict(baseline_mean=old, candidate_mean=new, reduction_percent=(1-new/old)*100)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "scenes"}, indent=2))


if __name__ == "__main__":
    main()
