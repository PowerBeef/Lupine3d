#!/usr/bin/env python3
"""Measure one exact tile-atlas candidate with the emitted SM83 program."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas_dir", type=Path)
    parser.add_argument("--profile", choices=("renderer-heavy", "entity-heavy"),
                        default="renderer-heavy")
    args = parser.parse_args()
    if args.profile == "renderer-heavy":
        os.environ["LUPINE3D_TILE_ATLAS_DIR"] = str(args.atlas_dir.resolve())
        os.environ["LUPINE3D_LEVEL"] = str((ROOT / "levels" / "renderer_benchmark.json").resolve())
    else:
        os.environ["LUPINE3D_ENTITY_ATLAS_DIR"] = str(args.atlas_dir.resolve())
    sys.path.insert(0, str(ROOT / "tools"))

    # Import only after selecting the candidate asset directory: layout.py
    # deliberately freezes generated assets at module-import time.
    import build_rom as br  # noqa: PLC0415
    from sm83emu import CGB  # noqa: PLC0415

    rom, assembler, _manifest = br.make_rom()
    cgb = CGB(rom, assembler.labels)
    cgb.run(until_pc=assembler.labels["main_loop"], max_steps=5_000_000)
    scenario = json.loads((ROOT / "playtests" / "coherence_tour.json").read_text(encoding="utf-8"))
    world_mode = str(scenario.get("world_mode", "empty")).lower()
    cgb.write8(br.WORLD_MODE, br.WORLD_MODE_EMPTY if world_mode == "empty" else br.WORLD_MODE_LIVING)
    masks = {"right": 0x01, "left": 0x02, "up": 0x04, "down": 0x08, "a": 0x10, "b": 0x20}
    cycles: list[int] = []
    dynamic_counts: list[int] = []
    for action in scenario["actions"]:
        if "pose" in action:
            x_q8, y_q8, angle = map(int, action["pose"])
            cgb.write16(br.PLAYER_XL, x_q8)
            cgb.write16(br.PLAYER_YL, y_q8)
            cgb.write8(br.ANGLE, angle)
        mask = sum(masks[str(button).lower()] for button in action.get("buttons", []))
        cgb.button_provider = lambda _iteration, _swaps, value=mask: value
        for _ in range(int(action.get("updates", 1))):
            before = cgb.cycles
            cgb.run(until_swaps=cgb.page_swaps + 1, max_steps=3_000_000)
            cycles.append(cgb.cycles - before)
            dynamic_counts.append(cgb.read8(br.DYN_COUNT))
            if cgb.read8(br.DYN_OVERFLOW):
                raise RuntimeError("candidate overflowed the dynamic tile buffer")

    result = {
        "rom_sha256": hashlib.sha256(rom).hexdigest(),
        "vram_profile": args.profile,
        "updates": len(cycles),
        "mean_cycles": statistics.fmean(cycles),
        "max_cycles": max(cycles),
        "min_updates_per_second": 8_388_608 / max(cycles),
        "mean_dynamic_tiles": statistics.fmean(dynamic_counts),
        "max_dynamic_tiles": max(dynamic_counts),
        "gdma_vblank_violations": cgb.gdma_vblank_violations,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
