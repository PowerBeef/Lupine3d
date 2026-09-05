#!/usr/bin/env python3
"""Controller-only completion gate. Reads state to steer; never writes game RAM.

This is an automated route/combat test, not a blind human legibility study.
Every completed image is checked against the geometry/compositor host models.
"""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path

import build_rom as br
from playtest import validate_frame, oam_budget, make_contact_sheet
from sm83emu import CGB, parse_symbols


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    rom = (br.BUILD / "lupine3d.gb").read_bytes()
    cgb = CGB(rom, parse_symbols(br.BUILD / "lupine3d.sym"))
    cgb.run(until_pc=cgb.symbols["main_loop"], max_steps=2_000_000)
    records, captures = [], []

    def live8(address):
        return cgb.wramx[2][address - 0xD000] if br.FIXED_SIMULATION and 0xD000 <= address < 0xE000 else cgb.read8(address)

    def live16(address):
        return live8(address) | live8(address + 1) << 8

    def pose():
        return live16(br.PLAYER_XL), live16(br.PLAYER_YL), live8(br.ANGLE)

    def step(keys=0):
        if len(records) >= 1200:
            raise AssertionError("controller route exceeded 1200-update watchdog")
        cgb.button_provider = (lambda *_: keys()) if callable(keys) else (lambda *_: keys)
        cycles = cgb.cycles
        cgb.run(until_swaps=cgb.page_swaps + 1, max_steps=3_000_000)
        data = validate_frame(cgb)
        data.update(oam_budget(cgb), keys="VBlank controller" if callable(keys) else keys, cycles=cgb.cycles - cycles,
                    health=live8(br.PLAYER_HEALTH))
        assert data["health"] > 0, "player died during controller-only route"
        assert data["max_oam_per_scanline"] <= 10
        assert cgb.commit_events[-1]["vblank_safe"]
        records.append(data)
        if len(records) % 50 == 0:
            print(f"Controller route: {len(records)} verified updates, pose={pose()}", flush=True)

    def capture(name):
        image = cgb.render_screen()
        image.save(output / f"{name}.png")
        captures.append((name, image))

    def turn(target):
        def steering():
            delta = (target - pose()[2] + 128) % 256 - 128
            return (1 if delta > 0 else 2) if abs(delta) > 1 else 0
        for _ in range(33):
            delta = (target - pose()[2] + 128) % 256 - 128
            if abs(delta) <= 2:
                return
            step(steering)
        raise AssertionError("turn watchdog")

    def path_to(goal):
        px, py, _ = pose()
        start = px >> 8, py >> 8
        queue, previous = deque([start]), {start: None}
        while queue:
            here = queue.popleft()
            if here == goal:
                path = []
                while here != start:
                    path.append(here); here = previous[here]
                return list(reversed(path))
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                nxt = here[0] + dx, here[1] + dy
                if nxt in previous or not (0 <= nxt[0] < 16 and 0 <= nxt[1] < 16):
                    continue
                if live8(br.MAP + nxt[1] * 16 + nxt[0]) not in (0, 3):
                    continue
                previous[nxt] = here; queue.append(nxt)
        raise AssertionError(f"no route to {goal}")

    def navigate(goal):
        for x, y in path_to(goal):
            tx, ty = x * 256 + 128, y * 256 + 128
            for _ in range(60):
                if live8(br.LEVEL_COMPLETE): return  # exit is a cell volume, not its centre
                px, py, _ = pose()
                dx, dy = tx - px, ty - py
                if abs(dx) <= 12 and abs(dy) <= 12:
                    break
                if abs(dx) > abs(dy):
                    target = 0 if dx > 0 else 128
                else:
                    target = 64 if dy > 0 else 192
                turn(target)
                # B pulses while approaching the next cell; only the ROM
                # decides whether a reachable, unlocked door can open.
                def walking():
                    px, py, _ = pose()
                    distance = abs(tx - px) if target in (0, 128) else abs(ty - py)
                    return (4 if distance > 8 else 0) | (32 if cgb.read16(br.SIM_CLOCK) & 8 else 0)
                step(walking)
            else:
                raise AssertionError(f"movement watchdog at {(x, y)}, pose={pose()}")

    capture("safe_start")
    navigate((8, 8)); capture("combat_approach")
    def aiming():
        px, py, angle = pose()
        dx, dy = live16(br.SENTINEL_XL) - px, live16(br.SENTINEL_YL) - py
        target = round(math.atan2(dy, dx) * 256 / math.tau) & 255
        delta = (target - angle + 128) % 256 - 128
        if abs(delta) > 1: return 1 if delta > 0 else 2
        return 16 if not cgb.read16(br.SIM_CLOCK) & 2 else 0
    for _ in range(20):
        if live8(br.SENTINEL_STATE) == br.SENTINEL_DEAD:
            break
        step(aiming)
    if live8(br.SENTINEL_STATE) != br.SENTINEL_DEAD:
        capture("combat_watchdog")
        raise AssertionError(f"Sentinel was not defeated: pose={pose()}, enemy="
                             f"{(live16(br.SENTINEL_XL),live16(br.SENTINEL_YL))}, "
                             f"health={live8(br.SENTINEL_HEALTH)}, player={live8(br.PLAYER_HEALTH)}")
    step(0)
    capture("sentinel_defeated")
    navigate((live8(br.SENTINEL_XH), live8(br.SENTINEL_YH)))
    step(0)
    assert cgb.read8(br.PICKUP_COLLECTED) == 1
    navigate((br.ACTIVE_LEVEL.exit.x, br.ACTIVE_LEVEL.exit.y))
    step(0)
    assert cgb.read8(br.LEVEL_COMPLETE) == 1
    capture("level_complete")
    report = {"passed": True, "rom_sha256": hashlib.sha256(rom).hexdigest(),
              "game_ram_injections": 0, "controller_only": True, "blind_navigation": False,
              "update_count": len(records), "health_remaining": cgb.read8(br.PLAYER_HEALTH),
              "sentinel_dead": True, "pickup_collected": True, "level_complete": True,
              "unsafe_gdma_starts": cgb.gdma_vblank_violations, "updates": records}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    make_contact_sheet(captures, output / "contact_sheet.png")
    print(json.dumps({k: v for k, v in report.items() if k != "updates"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=br.BUILD / "playthrough")
    run(parser.parse_args().output_dir)
