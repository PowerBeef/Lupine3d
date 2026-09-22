#!/usr/bin/env python3
"""Controller-only completion gate. Reads state to steer; never writes game RAM.

This is an automated route/combat test, not a blind human legibility study.
Every completed image is checked against the geometry/compositor host models.
The route plays the whole campaign: every sector is cleared, every drop is
collected and every intermission is crossed on controller input alone.
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
from sm83emu import CGB, parse_symbols, run_to_world


def run(output: Path, *, rom_path=None, symbols_path=None, restart=False, snapshot_mode="record"):
    output.mkdir(parents=True, exist_ok=True)
    rom = (rom_path or br.BUILD / "lupine3d.gb").read_bytes()
    cgb = CGB(rom, parse_symbols(symbols_path or br.BUILD / "lupine3d.sym"))
    run_to_world(cgb)
    records, captures, sectors = [], [], []
    # The route's captures are reviewable snapshots (suite `route`), recorded
    # rather than checked by default: where a capture lands depends on the
    # steering script, so a tuned route is not a visual regression.
    snapshots = None
    if snapshot_mode is not None:
        from snapshot import Suite, build_identity
        rom_sha = hashlib.sha256(rom).hexdigest(); built_sha, configuration_id = build_identity()
        snapshots = Suite("route", mode=snapshot_mode, rom_sha256=rom_sha,
                          configuration_id=configuration_id if built_sha == rom_sha else "foreign-rom")
    first_lcd=cgb.frame_count
    replay={}

    def live8(address):
        return cgb.wramx[2][address - 0xD000] if br.FIXED_SIMULATION and 0xD000 <= address < 0xE000 else cgb.read8(address)

    def live16(address):
        return live8(address) | live8(address + 1) << 8

    def pose():
        return live16(br.PLAYER_XL), live16(br.PLAYER_YL), live8(br.ANGLE)

    def latch(keys):
        # Latch one controller byte for each LCD interval. Steering may
        # inspect live state, but never changes midway through a P1 read.
        def controller(*_):
            frame=cgb.frame_count-first_lcd
            if frame not in replay: replay[frame]=keys() if callable(keys) else keys
            return replay[frame]
        return controller

    def step(keys=0):
        if len(records) >= 6000:
            raise AssertionError("controller route exceeded 6000-update watchdog")
        cgb.button_provider = latch(keys)
        cycles = cgb.cycles
        cgb.run(until_presentations=cgb.presentations + 1, max_steps=3_000_000)
        data = validate_frame(cgb)
        data.update(oam_budget(cgb), keys="VBlank controller" if callable(keys) else keys, cycles=cgb.cycles - cycles,
                    health=live8(br.PLAYER_HEALTH))
        if data["health"] <= 0:
            capture("death")
            recent = sorted(replay)[-90:]
            raise AssertionError(
                f"player died during controller-only route after {len(records)} updates: {situation()} "
                f"last frames (lcd frame, keys)={[(f, replay[f]) for f in recent]} "
                f"last updates (pose, health)={[((r['pose']['x_q8'], r['pose']['y_q8'], r['pose']['angle']), r['health']) for r in records[-30:]]}")
        assert data["max_oam_per_scanline"] <= 10
        assert cgb.commit_events[-1]["vblank_safe"]
        records.append(data)
        if len(records) % 50 == 0:
            print(f"Controller route: {len(records)} verified updates, pose={pose()}", flush=True)

    def drive(keys, predicate, why, limit=60_000_000):
        """Step the CPU directly. Screens publish nothing, so there is no
        presentation to wait for; the controller is still latched per LCD
        interval so the recorded tape replays the whole session."""
        cgb.button_provider = latch(keys)
        for _ in range(limit):
            if predicate(): return
            cgb.step()
        raise AssertionError(f"controller route stalled: {why}")

    def capture(name):
        image = cgb.render_screen()
        image.save(output / f"{name}.png")
        captures.append((name, image))
        if snapshots is not None and name not in snapshots.scenes:
            snapshots.observe(name, image)

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

    def shut_keycard_doors():
        """Door cells the ROM will refuse until a card is in hand.

        Read out of the live door table, like everything else the route
        steers by: no game-RAM writes and no build-time knowledge of which
        door is locked.
        """
        if live8(br.PLAYER_KEYS):
            return set()
        shut = set()
        for index in range(live8(br.DOOR_COUNT)):
            base = br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES
            if not live8(base + br.DOOR_FLAGS_OFFSET) & br.DOOR_FLAG_KEYCARD:
                continue
            if live8(base + br.DOOR_STATE_OFFSET) != 2:
                shut.add((live8(base + br.DOOR_X_OFFSET), live8(base + br.DOOR_Y_OFFSET)))
        return shut

    def path_to(goal, *, reachable_only=False):
        px, py, _ = pose()
        start = px >> 8, py >> 8
        closed = shut_keycard_doors()
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
                if live8(br.MAP + nxt[1] * 16 + nxt[0]) not in (0, 3) or nxt in closed:
                    continue
                previous[nxt] = here; queue.append(nxt)
        if reachable_only:
            return None
        raise AssertionError(f"no route to {goal}")

    def navigate(goal, stop=None):
        for x, y in path_to(goal):
            tx, ty = x * 256 + 128, y * 256 + 128
            stalled = 0
            for _ in range(90):
                if live8(br.LEVEL_COMPLETE): return  # exit is a cell volume, not its centre
                if stop is not None and stop(): return
                px, py, _ = pose()
                dx, dy = tx - px, ty - py
                if abs(dx) <= 12 and abs(dy) <= 12:
                    break
                # Drive the larger error, but the collision box spans four
                # cells: sitting on a boundary can make that axis unwalkable
                # while the other one clears the corner. Swap when stuck.
                along_x = abs(dx) > abs(dy)
                if stalled >= 6 and dx and dy:
                    along_x = not along_x
                target = (0 if dx > 0 else 128) if along_x else (64 if dy > 0 else 192)
                turn(target)
                # B pulses while approaching the next cell; only the ROM
                # decides whether a reachable, unlocked door can open.
                def walking():
                    px, py, angle = pose()
                    distance = abs(tx - px) if target in (0, 128) else abs(ty - py)
                    keys = (4 if distance > 8 else 0) | (32 if cgb.read16(br.SIM_CLOCK) & 8 else 0)
                    # Shoot whatever wanders into the crosshair on the way. The
                    # ROM decides whether the shot has a line; walking into a
                    # chaser without firing is how the route used to die.
                    quarry = nearest_living()
                    if quarry is not None and not cgb.read16(br.SIM_CLOCK) & 2:
                        heading = round(math.atan2(quarry["y"] - py, quarry["x"] - px) * 256 / math.tau) & 255
                        if abs((heading - angle + 128) % 256 - 128) <= 8:
                            keys |= 16
                    return keys
                before = pose()[:2]
                step(walking)
                stalled = stalled + 1 if pose()[:2] == before else 0
            else:
                raise AssertionError(f"movement watchdog at {(x, y)}, pose={pose()}")

    def slot_field(slot, offset):
        return live8(br.ENTITY_SLOTS + slot * 16 + offset)

    def actors():
        """Every bounded actor slot the loaded level declared. update_actors
        stores each slot before it restores the primary, so these are live."""
        return [{"slot": slot,
                 "x": slot_field(slot, 0) | slot_field(slot, 1) << 8,
                 "y": slot_field(slot, 2) | slot_field(slot, 3) << 8,
                 "state": slot_field(slot, 4), "health": slot_field(slot, 5),
                 "pickup": slot_field(slot, 10), "kind": slot_field(slot, br.ACTOR_KIND_OFFSET) & 3}
                for slot in range(live8(br.ACTOR_COUNT))]

    def doors():
        """The live door table: position, flags and state, as the ROM holds it."""
        return [{"x": live8(base + br.DOOR_X_OFFSET), "y": live8(base + br.DOOR_Y_OFFSET),
                 "flags": live8(base + br.DOOR_FLAGS_OFFSET), "state": live8(base + br.DOOR_STATE_OFFSET)}
                for base in (br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES for index in range(live8(br.DOOR_COUNT)))]

    def situation():
        """Everything a stalled route needs in its report to be diagnosable."""
        return (f"pose={pose()} health={live8(br.PLAYER_HEALTH)} keys={live8(br.PLAYER_KEYS)} "
                f"weapon={live8(br.WEAPON_INDEX)} actors={actors()} doors={doors()}")

    def living():
        return [actor for actor in actors() if actor["state"] != br.SENTINEL_DEAD]

    SWAP_SECTOR = 2        # the sector cleared with the second weapon
    ENGAGEMENT_Q8 = 1280   # five cells: shoot from range rather than walk into contact

    def nearest_living(*, walkable=False):
        px, py, _ = pose()
        alive = living()
        if walkable:
            # A card door shuts part of the sector until its carrier is dead,
            # so the route takes whoever it can actually walk to first.
            alive = [a for a in alive
                     if path_to((a["x"] >> 8, a["y"] >> 8), reachable_only=True) is not None]
        if not alive:
            return None
        return min(alive, key=lambda a: max(abs(a["x"] - px), abs(a["y"] - py)))

    def has_sight(actor):
        """Walk the live map along the shot. Proximity is not a clear line, and
        a closed panel counts as cover, so the route never fires into a wall.

        An exact diagonal changes both cell coordinates in one sample, so the
        two cells it squeezes between are checked as well: a shot does not pass
        through a wall corner, whatever the sampling rate.
        """
        px, py, _ = pose()
        solid = lambda cx, cy: live8(br.MAP + cy * 16 + cx)
        steps = max(abs(actor["x"] - px), abs(actor["y"] - py)) // 32 + 1
        cell = px >> 8, py >> 8
        for sample in range(1, steps + 1):
            x = (px + (actor["x"] - px) * sample // steps) >> 8
            y = (py + (actor["y"] - py) * sample // steps) >> 8
            if solid(x, y):
                return False
            if x != cell[0] and y != cell[1] and (solid(cell[0], y) or solid(x, cell[1])):
                return False
            cell = x, y
        return True

    def engageable(target=None):
        # Judge the actor the route is actually hunting: the nearest one it can
        # walk to, which is what clear_sector chose. The nearest of all can be
        # one cell away through a wall, and no exchange settles that.
        target = nearest_living(walkable=True) if target is None else target
        if target is None:
            return True
        px, py, _ = pose()
        dx, dy = abs(target["x"] - px), abs(target["y"] - py)
        # An actor at contact range is fought where it stands when a shot can
        # reach it, or when it is already on the attack: aiming backs away from
        # it while firing, and walking towards it is how the route dies. A
        # patroller one cell away behind a wall or a shut panel is neither,
        # and firing at the wall from here would never clear the sector.
        if dx < 512 and dy < 512:
            return has_sight(target) or target["state"] in (br.SENTINEL_CHASE, br.SENTINEL_ATTACK)
        return max(dx, dy) <= ENGAGEMENT_Q8 and has_sight(target)

    hold_aim = [False]  # set while an exchange has proved that kiting settles nothing

    def aiming():
        # Re-pick the nearest survivor every interval: whoever closed to
        # contact is the one answering fire, not the one we set out to kill.
        target = nearest_living()
        if target is None:
            return 0
        px, py, angle = pose()
        dx, dy = target["x"] - px, target["y"] - py
        heading = round(math.atan2(dy, dx) * 256 / math.tau) & 255
        delta = (heading - angle + 128) % 256 - 128
        # Keep steering to the target rather than parking one degree away:
        # at close range the legacy Q4 transform can put that pose outside
        # the aim window. Fire while making the final small correction, and
        # back away from anything already at contact range: every AI tick
        # spent adjacent costs health, and stepping back also moves the shot
        # off a corner the actor may be pressed against.
        # Contact is cell adjacency: the ROM attacks when both cell deltas
        # are below two, whatever the fraction, so kite from inside two cells.
        contact = abs(dx) < 512 and abs(dy) < 512 and not hold_aim[0]
        return ((1 if delta > 0 else 2) if delta else 0) | (8 if contact else 0) | \
               (16 if abs(delta) <= 8 and not cgb.read16(br.SIM_CLOCK) & 2 else 0)

    def reposition(actor):
        """The cell to shoot from next when firing from here settles nothing."""
        px, py, _ = pose()
        here = px >> 8, py >> 8
        dx, dy = here[0] - (actor["x"] >> 8), here[1] - (actor["y"] >> 8)
        away = (1 if dx > 0 else -1 if dx < 0 else 0, 0) if abs(dx) >= abs(dy) else (0, 1 if dy > 0 else -1)
        candidates = [(here[0] + away[0], here[1] + away[1]),
                      (here[0] + away[1], here[1] + away[0]), (here[0] - away[1], here[1] - away[0])]
        for cell in candidates:
            if path_to(cell, reachable_only=True) is not None and cell != here:
                return cell
        return actor["x"] >> 8, actor["y"] >> 8

    def swap_weapon():
        """Press SELECT and let the ROM stream the other weapon's patterns in.

        Every frame of it goes through step(), so the pattern transfer is
        checked for a start outside VBlank like any other publication.
        """
        before = live8(br.WEAPON_INDEX)
        for _ in range(6):
            step(0x40)
            if live8(br.WEAPON_INDEX) != before:
                break
        else:
            raise AssertionError("SELECT did not swap the weapon")
        for _ in range(6):
            step(0)
            if not live8(br.WEAPON_RELOAD):
                return
        raise AssertionError("the weapon patterns were never streamed")

    def collect_drops():
        """Walk onto every drop the route can reach and has not taken."""
        for actor in actors():
            if not actor["pickup"]:
                continue
            cell = actor["x"] >> 8, actor["y"] >> 8
            if path_to(cell, reachable_only=True) is None:
                continue
            navigate(cell); step(0)

    def clear_sector(name):
        """Kill every actor the route can walk to, taking drops as it goes."""
        opened = cgb.frame_count
        fruitless = {}  # exchanges per actor slot that killed nothing
        while living():
            if cgb.frame_count - opened > 12_000:
                capture(f"{name}_combat_watchdog")
                raise AssertionError(f"sector {name} was not cleared after {len(records)} updates: {situation()}")
            target = nearest_living(walkable=True)
            if target is None:
                # Everything left is behind a door that wants a card: take the
                # drops on this side and the way through opens.
                collect_drops()
                assert nearest_living(walkable=True) is not None, \
                    f"sector {name} deadlocked: {situation()}"
                continue
            if not engageable(target):
                navigate((target["x"] >> 8, target["y"] >> 8), stop=engageable)
                continue
            # Cached presentations can run much faster than simulation
            # cooldowns. Bound each exchange by LCD time, not render cadence,
            # and by less of it when the target is already in contact range:
            # every AI tick it spends adjacent costs health.
            exchange, opening = cgb.frame_count, len(living())
            px, py, _ = pose()
            contact = abs(target["x"] - px) < 512 and abs(target["y"] - py) < 512
            # Two exchanges that settled nothing mean kiting is what keeps the
            # shot off the actor: stand and hold the aim for the next one.
            hold_aim[0] = fruitless.get(target["slot"], 0) >= 2
            while living() and engageable() and cgb.frame_count - exchange < (120 if contact else 300):
                step(aiming)
            hold_aim[0] = False
            survivor = nearest_living(walkable=True)
            if len(living()) < opening:
                fruitless.clear()
            elif survivor is not None:
                count = fruitless[survivor["slot"]] = fruitless.get(survivor["slot"], 0) + 1
                if count >= 4:
                    # Nothing shot from anywhere nearby has reached it: walk
                    # onto its own cell, where no corner is left to hide behind.
                    fruitless[survivor["slot"]] = 0
                    navigate((survivor["x"] >> 8, survivor["y"] >> 8))
                elif engageable(survivor):
                    # The shot had a host-side line but the ROM's exact centre
                    # ray did not reach the actor: it stands against a corner
                    # the sampled line squeezed past. Standing still and firing
                    # is how the route dies now, so move one cell and change
                    # the line - back along the shot if that cell is open,
                    # otherwise onto the actor's own cell.
                    navigate(reposition(survivor))
                else:
                    # Close the distance only while the shot still cannot
                    # reach; walking onto a live chaser is how the route used
                    # to die.
                    navigate((survivor["x"] >> 8, survivor["y"] >> 8), stop=engageable)
        step(0)
        collect_drops()

    def cross_screen(expected_mode, name):
        """A results screen owns the whole background and publishes nothing."""
        drive(0, lambda: cgb.read8(br.GAME_MODE) != br.MODE_PLAYING, "no results screen")
        assert cgb.read8(br.GAME_MODE) == expected_mode, cgb.read8(br.GAME_MODE)
        drive(0, lambda: cgb.io[0x40] == 0x81, "results screen never displayed")
        capture(name)
        # START is released before the world returns, so the ROM's own edge
        # shadow clears itself across the VBlanks that rebuild the world.
        drive(0x80, lambda: cgb.read8(br.GAME_MODE) == br.MODE_PLAYING, "START was not accepted")
        drive(0, lambda: cgb.pc == cgb.symbols["main_loop"], "the world never came back")
        cgb.button_provider = None; cgb.buttons = 0

    # The route follows the ROM under test, not the build-time source: a
    # pinned baseline carries one compile-time level and no results screens.
    campaign = br.CAMPAIGN if "select_level" in cgb.symbols else br.CAMPAIGN[:1]
    for index, level in enumerate(campaign):
        if "select_level" in cgb.symbols:
            assert cgb.read8(br.LEVEL_INDEX) == index, (index, cgb.read8(br.LEVEL_INDEX))
            assert cgb.read8(br.LEVEL_BANK) == br.LEVEL_ROM_BANK_BASE + index
        assert bytes(live8(br.MAP + cell) for cell in range(256)) == level.grid
        opened = len(records)
        capture(f"sector{index + 1}_start")
        # One sector is cleared with the other weapon, so the pattern stream
        # that swaps it runs under the same frame-by-frame checks as
        # everything else - including the one for a transfer outside VBlank.
        if "swap_weapon" in cgb.symbols and index == SWAP_SECTOR:
            swap_weapon(); capture(f"sector{index + 1}_second_weapon")
        clear_sector(f"sector{index + 1}")
        if "swap_weapon" in cgb.symbols and index == SWAP_SECTOR:
            swap_weapon()
        capture(f"sector{index + 1}_cleared")
        navigate((level.exit.x, level.exit.y))
        step(0)
        assert live8(br.LEVEL_COMPLETE) == 1
        assert all(actor["state"] == br.SENTINEL_DEAD for actor in actors())
        assert live8(br.PICKUP_COLLECTED) == 1
        sectors.append({"index": index, "name": level.name, "updates": len(records) - opened,
                        "actors": live8(br.ACTOR_COUNT), "health_remaining": live8(br.PLAYER_HEALTH)})
        capture(f"sector{index + 1}_complete")
        print(f"Sector {index + 1} ({level.name}) complete after {len(records)} updates", flush=True)
        if index + 1 < len(campaign):
            generation = cgb.read16(br.WALL_EPOCH)
            cross_screen(br.MODE_INTERMISSION, f"sector{index + 2}_intermission")
            assert cgb.read16(br.WALL_EPOCH) != generation
            assert not live8(br.LEVEL_COMPLETE) and live8(br.PLAYER_HEALTH) == 99

    completed_at=len(records)
    if restart:
        generation=cgb.read16(br.WALL_EPOCH)
        if "select_level" in cgb.symbols:
            # The last sector ends the campaign; the ending screen restarts it.
            cross_screen(br.MODE_ENDING, "campaign_ending")
            assert cgb.read8(br.LEVEL_INDEX) == 0
        else:
            # A pinned baseline freezes on completion and reloads on START.
            step(128); step(0)
            for _ in range(8):
                if not live8(br.LEVEL_COMPLETE) and cgb.read16(br.WALL_EPOCH)!=generation: break
                step(0)
        assert not live8(br.LEVEL_COMPLETE) and cgb.read16(br.WALL_EPOCH)!=generation
        assert live8(br.PLAYER_HEALTH)==99 and live8(br.PICKUP_COLLECTED)==0
        step(0)
        capture("restarted")
    tape=bytes(replay.get(i,0) for i in range(cgb.frame_count-first_lcd+1))
    (output/'controller_replay.bin').write_bytes(tape)
    report = {"passed": True, "rom_sha256": hashlib.sha256(rom).hexdigest(),
              "game_ram_injections": 0, "controller_only": True, "blind_navigation": False,
              "schema":"lupine3d.controller-route.v3","input_replay_sha256":hashlib.sha256(tape).hexdigest(),
              "input_replay_encoding":"one controller byte per LCD interval; adaptive controller recorded for replay",
              "lcd_intervals":len(tape),"completion_update":completed_at,"restart_verified":restart,
              "campaign_levels":len(campaign),"sectors":sectors,
              "update_count": len(records), "health_remaining": cgb.read8(br.PLAYER_HEALTH),
              "sentinel_dead": True, "pickup_collected": True, "level_complete": True,
              "unsafe_gdma_starts": cgb.gdma_vblank_violations, "updates": records}
    if snapshots is not None:
        report["snapshot"] = snapshots.report()
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    make_contact_sheet(captures, output / "contact_sheet.png")
    print(json.dumps({k: v for k, v in report.items() if k != "updates"}, indent=2))
    if snapshots is not None:
        snapshots.finish()  # raises in check mode when a capture differs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=br.BUILD / "playthrough")
    parser.add_argument("--rom",type=Path);parser.add_argument("--symbols",type=Path)
    parser.add_argument("--restart",action="store_true")
    parser.add_argument("--snapshot-mode",choices=("check","record","none"),default="record")
    args=parser.parse_args()
    if bool(args.rom)!=bool(args.symbols):parser.error("Supply ROM and symbols together")
    run(args.output_dir,rom_path=args.rom,symbols_path=args.symbols,restart=args.restart,
        snapshot_mode=None if args.snapshot_mode=="none" else args.snapshot_mode)
