#!/usr/bin/env python3
"""Profile actual generated code by main-loop stage, including IRQ/wait cost."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

import build_rom as br
from playtest import button_mask, validate_frame, set_test_world_byte, apply_diagnostic_camera
from sm83emu import CGB


def profile(scenario_file):
    rom, asm, _ = br.make_rom()
    cgb = CGB(rom, asm.labels)
    cgb.run(until_pc=asm.labels["main_loop"])
    scenario = json.loads(scenario_file.read_text())
    set_test_world_byte(cgb, br.WORLD_MODE, int(scenario.get("world_mode") != "empty"))
    names = ("begin_frame_snapshot", "cast_all", "render_view", "render_entities",
             "populate_reprojection_guards", "upload_hidden_page")
    starts = {asm.labels[n]: n for n in names}
    totals, updates, captures = Counter(), [], {}
    stage = "publication_tail"
    service_return = None
    original = cgb.step
    def measured_step():
        nonlocal stage, service_return
        if service_return and (cgb.pc, cgb.sp) == service_return[:2]:
            stage = service_return[2]; service_return = None
        stage = starts.get(cgb.pc, stage)
        if cgb.pc == asm.labels["render_yield"]:
            service_return = (cgb.read16(cgb.sp), (cgb.sp + 2) & 65535, stage)
            stage = "simulation_service"
        before = cgb.cycles
        result = original()
        totals[stage] += cgb.cycles - before
        return result
    cgb.step = measured_step
    for action in scenario["actions"]:
        apply_diagnostic_camera(cgb, action)
        mask = button_mask(action.get("buttons", []))
        cgb.button_provider = lambda *_, value=mask: value
        for _ in range(action.get("updates", 1)):
            before = cgb.cycles
            cgb.run(until_swaps=cgb.page_swaps + 1)
            validate_frame(cgb)
            updates.append(cgb.cycles - before)
        if "capture" in action:
            captures[action["capture"]] = hashlib.sha256(cgb.render_screen().tobytes()).hexdigest()
    return {"updates": len(updates), "mean_cycles": statistics.fmean(updates), "max_cycles": max(updates),
            "stage_mean_cycles": {key: value / len(updates) for key, value in totals.items()},
            "capture_rgb_sha256": captures}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=br.BUILD / "profile.json")
    args = parser.parse_args()
    result = {"folded": br.FOLDED_COMPOSITOR, "atlas_patterns": br.TILE_ATLAS_COUNT,
              "rom_sha256": hashlib.sha256(br.make_rom()[0]).hexdigest(),
              "routes": {name: profile(br.ROOT / "playtests" / name)
                         for name in ("coherence_tour.json", "living_world.json")}}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
