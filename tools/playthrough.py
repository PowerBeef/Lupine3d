#!/usr/bin/env python3
"""Controller-only completion gate. Reads state to steer; never writes game RAM.

This is an automated route/combat test, not a blind human legibility study.
Every completed image is checked against the geometry/compositor host models.
The route plays the whole campaign: every sector is cleared, every drop is
collected and every intermission is crossed on controller input alone.
`LUPINE3D_ROUTE_DEBUG=1` traces every combat exchange; a death report names
the sector, and `--sectors N-N` replays that sector alone from its code.
"""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path

import build_rom as br
from playtest import validate_frame, oam_budget, make_contact_sheet
from sm83emu import CGB, parse_symbols, run_to_world



def enter_sector(cgb, level: int) -> None:
    """Start the campaign at sector `level` (0-based) the way a player would:
    the continue code the ROM prints for it, typed on the title with the
    controller. Nothing is written to game RAM; the code table is the build's."""
    from lupine3d_v4.screens import continue_codes
    cgb.button_provider = lambda *_: 0
    for _ in range(2_000_000):
        if cgb.read8(br.GAME_MODE) == br.MODE_TITLE and cgb.io[0x40] & 0x80:
            break
        cgb.step()
    else:
        raise AssertionError("the title never appeared")

    def press(button, steps=160_000):
        # Selection follows rising edges, so every press is a release too.
        for held in (button, 0):
            cgb.button_provider = lambda *_, value=held: value
            for _ in range(steps):
                cgb.step()

    code = continue_codes(br.LEVEL_COUNT, br.DIFFICULTY_LEVELS)[level * br.DIFFICULTY_LEVELS + cgb.read8(br.DIFFICULTY)]
    press(0x40)                                   # SELECT opens code entry
    assert cgb.read8(br.SCREEN_INDEX) == br.SCREEN_PASSWORD, "SELECT did not open code entry"
    for index, digit in enumerate(code):
        for _ in range(digit):
            press(0x04)                           # up rolls the digit
        if index < len(code) - 1:
            press(0x01)                           # right moves the cursor
    assert [cgb.read8(br.SCREEN_DIGITS + i) for i in range(br.PASSWORD_DIGITS)] == list(code)
    press(0x80)                                   # START accepts
    # A code into a later episode shows that episode's opening first; it
    # waits for its own START like any screen.
    from lupine3d_v4.screens import SCREEN_EPISODE_OPENINGS
    for _ in range(1 + len(SCREEN_EPISODE_OPENINGS)):
        cgb.button_provider = lambda *_: 0
        for _ in range(2_000_000):
            if cgb.read8(br.GAME_MODE) == br.MODE_PLAYING and cgb.pc == cgb.symbols["main_loop"]:
                break
            if cgb.io[0x40] & 0x80 and cgb.read8(br.SCREEN_INDEX) in SCREEN_EPISODE_OPENINGS and cgb.pc == cgb.symbols["screen_wait_start"]:
                press(0x80)
                break
            cgb.step()
        else:
            raise AssertionError(f"the code for sector {level + 1} did not start the world")
        if cgb.read8(br.GAME_MODE) == br.MODE_PLAYING:
            break
    else:
        raise AssertionError(f"the code for sector {level + 1} never left the episode screens")
    assert cgb.read8(br.LEVEL_INDEX) == level, (cgb.read8(br.LEVEL_INDEX), level)
    cgb.button_provider = None


def run(output: Path, *, rom_path=None, symbols_path=None, restart=False, snapshot_mode="record",
        sectors=None):
    # The route plays the game as it ships. The evidence population (the
    # frozen v0.12 first sector the engine's evidence runs on) is not a game.
    if br.level_codec.population() != "shipped":
        raise SystemExit("the route plays the shipped game; unset LUPINE3D_POPULATION")
    output.mkdir(parents=True, exist_ok=True)
    rom = (rom_path or br.GAME_BUILD / "lupine3d.gb").read_bytes()
    cgb = CGB(rom, parse_symbols(symbols_path or br.GAME_BUILD / "lupine3d.sym"))
    # The route follows the ROM under test, not the build-time source: a
    # pinned baseline carries one compile-time level and no results screens.
    campaign = br.CAMPAIGN if "select_level" in cgb.symbols else br.CAMPAIGN[:1]
    first, last = sectors or (1, len(campaign))
    if not 1 <= first <= last <= len(campaign):
        raise ValueError(f"sectors {first}-{last} are not within 1-{len(campaign)}")
    if restart and last != len(campaign):
        raise ValueError("--restart needs the route to reach the last sector")
    if first > 1:
        enter_sector(cgb, first - 1)
    run_to_world(cgb)
    # A budget, not a gate: the later episodes are three-by-three room grids
    # with up to six actors and six doors, and their measured sectors run to
    # about 3,900 updates against episode one's 350-1,300. A chunk of three
    # spends its budget as a whole, so one long sector borrows from short ones.
    watchdog = 3500 * (last - first + 1)
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
        # The live world, not the presented frame the harness shows right
        # after a presentation (overlapped publication, docs/explanation/verification.md).
        return cgb.live_wramx[2][address - 0xD000] if br.FIXED_SIMULATION and 0xD000 <= address < 0xE000 else cgb.read8(address)

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
        if len(records) >= watchdog:
            raise AssertionError(f"controller route exceeded its {watchdog}-update watchdog")
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

    def turn(target, stop=None):
        def steering():
            delta = (target - pose()[2] + 128) % 256 - 128
            return (1 if delta > 0 else 2) if abs(delta) > 1 else 0
        for _ in range(33):
            delta = (target - pose()[2] + 128) % 256 - 128
            if abs(delta) <= 2 or (stop is not None and stop()):
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
                # A turn under a chaser costs contacts too: the walk's stop
                # rule ends it as it ends a step. Cryo Vault's warden took
                # seventy health off turns that ignored it.
                turn(target, stop)
                if stop is not None and stop(): return
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

    exchanges = []  # one record per combat exchange, for the failure report

    def situation():
        """Everything a stalled route needs in its report to be diagnosable."""
        return (f"pose={pose()} health={live8(br.PLAYER_HEALTH)} keys={live8(br.PLAYER_KEYS)} "
                f"weapon={live8(br.WEAPON_INDEX)} actors={actors()} doors={doors()} "
                f"last exchanges={exchanges[-8:]}")

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

    def has_sight(actor, origin=None):
        """Walk the live map along the shot. Proximity is not a clear line, and
        a closed panel counts as cover, so the route never fires into a wall.

        An exact diagonal changes both cell coordinates in one sample, so the
        two cells it squeezes between are checked as well: a shot does not pass
        through a wall corner, whatever the sampling rate.
        """
        px, py = pose()[:2] if origin is None else origin
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

    DEBUG = bool(os.environ.get("LUPINE3D_ROUTE_DEBUG"))   # trace every exchange
    hold_aim = [False]  # set while an exchange has proved that kiting settles nothing
    fired = [0]         # shots the current exchange has actually taken

    kind_stats = cgb.symbols.get("actor_kind_stats")

    def contact_damage(actor):
        """What one AI tick beside this actor costs, from the ROM's own kind table."""
        if kind_stats is None:
            return 8
        authored = rom[kind_stats + (actor["kind"] & 3) * br.ACTOR_KIND_RECORD_BYTES]
        return (authored // 2, authored, authored + authored // 2)[live8(br.DIFFICULTY)]

    def survives_contact(actor):
        # Standing beside an actor costs a contact per AI tick until the shot
        # lands; a warden takes a third of the bar each time. Only close in
        # when two of them still leave the route alive.
        return live8(br.PLAYER_HEALTH) > 2 * contact_damage(actor)

    def ray_clear(heading, target):
        """The ROM scores a shot by its centre ray: the first wall along the
        heading occludes the actor behind it. March that ray over the live
        map to just short of the actor, so the route never keeps firing a
        heading that grazes a wall corner. Signal Deck's and Cryo Vault's
        diagonal neighbours soaked up dozens of axis shots that way."""
        px, py, _ = pose()
        reach = math.hypot(target["x"] - px, target["y"] - py) - 64
        ux, uy = math.cos(heading * math.tau / 256), math.sin(heading * math.tau / 256)
        travelled = 0.0
        while travelled < reach:
            travelled += 16
            cx, cy = int(px + ux * travelled) >> 8, int(py + uy * travelled) >> 8
            if not (0 <= cx < 16 and 0 <= cy < 16) or live8(br.MAP + cy * 16 + cx):
                return False
        return True

    def attacker():
        """An actor already swinging at the route from contact range: the one
        to answer first, whoever the route set out to kill."""
        px, py, _ = pose()
        swinging = [a for a in living() if a["state"] == br.SENTINEL_ATTACK
                    and abs(a["x"] - px) < 512 and abs(a["y"] - py) < 512 and has_sight(a)]
        return min(swinging, key=lambda a: max(abs(a["x"] - px), abs(a["y"] - py))) if swinging else None

    def aiming():
        # Re-pick every interval: an actor swinging from contact range first,
        # else the nearest survivor. Whoever closed to contact is the one
        # answering fire, not the one we set out to kill.
        target = attacker() or nearest_living()
        if target is None:
            return 0
        px, py, angle = pose()
        dx, dy = target["x"] - px, target["y"] - py
        heading = exact = round(math.atan2(dy, dx) * 256 / math.tau) & 255
        # A target all but on the route's own row or column is shot straight
        # down the axis: a heading one step off it drifts into the next row
        # and grazes a wall the line itself clears. Antenna Base's warden, on
        # its row's very edge, took ninety shots into a corner that way. Only
        # while the axis keeps it within six pixels of the crosshair (focal
        # 137 px, so 23 units along per unit across): further off, the axis
        # shot leaves the aim window, as Coolant Dark's Sentinel showed.
        if abs(dy) * 23 < abs(dx):
            heading = 0 if dx > 0 else 128
        elif abs(dx) * 23 < abs(dy):
            heading = 64 if dy > 0 else 192
        # ... unless that axis runs into a wall before the actor: then the
        # exact bearing, which may still clear the corner.
        if heading != exact and not ray_clear(heading, target):
            heading = exact
        delta = (heading - angle + 128) % 256 - 128
        # Keep steering to the target rather than parking one degree away:
        # at close range the legacy Q4 transform can put that pose outside
        # the aim window. Fire while making the final small correction, and
        # back away from anything already at contact range: every AI tick
        # spent adjacent costs health, and stepping back also moves the shot
        # off a corner the actor may be pressed against.
        # Contact is cell adjacency: the ROM attacks when both cell deltas
        # are below two, whatever the fraction, so kite from inside two cells.
        # Kite along the line of fire only: backing away while still turning
        # towards the actor moves the route wherever it happens to face, and
        # in Signal Deck that was into a doorway around a wall corner, where
        # the line was lost before a shot went out, every exchange over.
        contact = abs(dx) < 512 and abs(dy) < 512 and not hold_aim[0]
        retreat = contact and abs(delta) <= 16
        shoot = abs(delta) <= 8 and not cgb.read16(br.SIM_CLOCK) & 2
        fired[0] += shoot
        return ((1 if delta > 0 else 2) if delta else 0) | (8 if retreat else 0) | (16 if shoot else 0)

    def firing_cell(actor):
        """The nearest reachable cell two to five cells from the actor with a
        host line to it. The ROM's contact rule is cell adjacency, diagonals
        included, so an actor across a wall corner can reach the route while
        no shot reaches it: the answer is to leave the adjacency and shoot
        from a cell with a line, never to stand there trading health."""
        ax, ay = actor["x"] >> 8, actor["y"] >> 8
        best = None
        for cy in range(1, 15):
            for cx in range(1, 15):
                distance = max(abs(cx - ax), abs(cy - ay))
                if not 2 <= distance <= 6 or live8(br.MAP + cy * 16 + cx):
                    continue
                if not has_sight(actor, origin=(cx * 256 + 128, cy * 256 + 128)):
                    continue
                path = path_to((cx, cy), reachable_only=True)
                if path is None or any(max(abs(x - ax), abs(y - ay)) <= 1 for x, y in path):
                    continue                   # never walk past it to get there
                # A cell on the actor's own row or column first, and the
                # farther the better: a chaser then comes straight down the
                # line of fire and stays in the crosshair while it does.
                rank = (0 if cx == ax or cy == ay else 1, -distance if cx == ax or cy == ay else len(path))
                if best is None or rank < best[0]:
                    best = (rank, (cx, cy))
        return None if best is None else best[1]

    def face(actor):
        """Turn to the actor at once: the walk away leaves the route facing the
        wrong way, and every update spent turning under a chaser costs health.
        Another actor already swinging from contact range is faced instead."""
        actor = attacker() or actor
        px, py, _ = pose()
        turn(round(math.atan2(actor["y"] - py, actor["x"] - px) * 256 / math.tau) & 255)

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
            # shot off the actor: stand and hold the aim for the next one -
            # unless standing still beside it would be the death of the route.
            # Holding still beside an actor that is already chasing or attacking
            # is how the route dies; kiting is right against one that comes.
            hold_aim[0] = (fruitless.get(target["slot"], 0) >= 2 and survives_contact(target)
                           and target["state"] not in (br.SENTINEL_CHASE, br.SENTINEL_ATTACK))
            start_health = live8(br.PLAYER_HEALTH)
            fired[0] = 0
            record = {"update": len(records), "target": target["slot"], "kind": target["kind"],
                      "state": target["state"], "at": (target["x"], target["y"]), "from": (px, py),
                      "health": start_health, "target_health": target["health"],
                      "contact": contact, "hold": hold_aim[0]}
            aimed_health = None   # health when the first shot went out
            while living() and engageable() and cgb.frame_count - exchange < (120 if contact else 300):
                step(aiming)
                if fired[0] and aimed_health is None:
                    aimed_health = live8(br.PLAYER_HEALTH)
                if DEBUG:
                    t = next((a for a in actors() if a["slot"] == target["slot"]), None)
                    print("  exchange", len(records), "pose", pose(), "hp", live8(br.PLAYER_HEALTH), "target", t,
                          "sight", t and has_sight(t), "walkable", t and path_to((t["x"] >> 8, t["y"] >> 8), reachable_only=True) is not None,
                          "engageable", engageable(), "fired", fired[0], flush=True)
                # Two contacts taken and nothing dealt: this line does not
                # reach it, and every further frame here only costs health.
                # Only once a shot has actually gone out, though: an exchange
                # that was still turning to face a chaser has proved nothing,
                # and leaving it turns the route away again, so the aim is
                # never reached and every re-decision costs another contact.
                # Signal Deck's last skirmisher killed the route that way. So
                # the two contacts are counted from the first shot: the hits
                # taken turning to face it say nothing about the line, and
                # leaving on them walked Cryo Vault's route into its warden.
                if (aimed_health is not None and live8(br.PLAYER_HEALTH) <= aimed_health - 2 * contact_damage(target)
                        and next((a["health"] for a in actors() if a["slot"] == target["slot"]), 0) == target["health"]):
                    record["decision"] = "cut short"
                    break
            hold_aim[0] = False
            survivor = nearest_living(walkable=True)
            after = next((a for a in actors() if a["slot"] == target["slot"]), target)
            record.update(frames=cgb.frame_count - exchange, shots=fired[0], target_health_after=after["health"],
                          target_state_after=after["state"], health_after=live8(br.PLAYER_HEALTH))
            exchanges.append(record)
            if DEBUG:
                print(" record", record, flush=True)
            px, py, _ = pose()
            adjacent = abs((px >> 8) - (after["x"] >> 8)) <= 1 and abs((py >> 8) - (after["y"] >> 8)) <= 1
            if after["state"] != br.SENTINEL_DEAD and after["health"] == target["health"] and adjacent:
                # Beside it and nothing landed: the ROM's ray is blocked by a
                # corner its contact rule ignores. Leave the adjacency for the
                # nearest cell with a line and hold the aim from there.
                cell = firing_cell(after)
                if cell is not None:
                    record["decision"] = f"firing position {cell}"
                    fruitless[target["slot"]] = max(fruitless.get(target["slot"], 0), 2)
                    # Two contacts taken on the way means the actor is in the
                    # way or on the route's heels: turn and fight it where the
                    # route stands. Antenna Base's warden, blocking the walk,
                    # took the whole bar while the route kept walking into it.
                    walk_health = live8(br.PLAYER_HEALTH)
                    navigate(cell, stop=lambda: live8(br.PLAYER_HEALTH) <= walk_health - 2 * contact_damage(after))
                    chaser = next((a for a in living() if a["slot"] == target["slot"]), None)
                    if chaser is not None:
                        face(chaser)
                    continue
            if len(living()) < opening:
                fruitless.clear()
            elif survivor is not None:
                count = fruitless[survivor["slot"]] = fruitless.get(survivor["slot"], 0) + 1
                awake = survivor["state"] in (br.SENTINEL_CHASE, br.SENTINEL_ATTACK)
                if count >= 4 and (awake or not survives_contact(survivor)):
                    # Walking onto an actor that is already coming, or one the
                    # bar cannot afford to stand beside, is how the route dies:
                    # a warden takes a third of it per contact and a long walk
                    # is many contacts. Take a drop already on the floor if one
                    # is reachable, otherwise change the line from one cell
                    # away and keep trading from range; it will come to us.
                    fruitless[survivor["slot"]] = 2
                    record["decision"] = "reposition"
                    if any(a["pickup"] and path_to((a["x"] >> 8, a["y"] >> 8), reachable_only=True) is not None
                           for a in actors()) and not survives_contact(survivor):
                        collect_drops()
                    else:
                        # The actor is awake and follows: a walk it keeps
                        # striking is contacts taken for nothing. Two of them
                        # on the way means it is on the route's heels, so turn
                        # and fight it where the route stands, as the walk to
                        # a firing position does. Sable Outpost's Sentinel took
                        # seven contacts off a 130-update reposition that way
                        # once cheaper middle-distance cels shifted the timing.
                        walk_health = live8(br.PLAYER_HEALTH)
                        navigate(reposition(survivor),
                                 stop=lambda: live8(br.PLAYER_HEALTH) <= walk_health - 2 * contact_damage(survivor))
                        chaser = next((a for a in living() if a["slot"] == survivor["slot"]), None)
                        if chaser is not None:
                            face(chaser)
                elif count >= 4:
                    # Nothing shot from anywhere nearby has reached a dormant
                    # or patrolling actor: walk onto its own cell, where no
                    # corner is left to hide behind, while the bar can take it.
                    # Stop once the walk is costing health and a step has
                    # brought it beside the actor with a line: walking on past
                    # a line while it swings at the route is how Reactor
                    # Gate's warden killed it (seven contacts, no shot). A walk
                    # nothing is hitting goes on to the actor's cell: stopping
                    # it early sends the route back into the corner fight
                    # Reactor Heart's boss wins.
                    fruitless[survivor["slot"]] = 0
                    record["decision"] = "close in"
                    slot, walk_health = survivor["slot"], live8(br.PLAYER_HEALTH)
                    walk_x, walk_y, _ = pose()

                    def lined_up():
                        live = next((a for a in living() if a["slot"] == slot), None)
                        if live is None:
                            return True
                        x, y, _ = pose()
                        beside = abs(live["x"] - x) < 512 and abs(live["y"] - y) < 512
                        return (live8(br.PLAYER_HEALTH) < walk_health and (x >> 8, y >> 8) != (walk_x >> 8, walk_y >> 8)
                                and beside and has_sight(live))
                    navigate((survivor["x"] >> 8, survivor["y"] >> 8),
                             stop=lambda: not survives_contact(survivor) or lined_up())
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
        # shadow clears itself across the VBlanks that rebuild the world. An
        # intermission that crossed into the next episode shows that
        # episode's closing and opening on the way, each on its own START;
        # the ending returns to the title, whose START leads to the prologue.
        from lupine3d_v4.screens import SCREEN_EPISODE_CLOSINGS, SCREEN_EPISODE_OPENINGS
        episode_screens = SCREEN_EPISODE_CLOSINGS + SCREEN_EPISODE_OPENINGS
        if expected_mode == br.MODE_ENDING:
            episode_screens += (br.SCREEN_TITLE,)
        shown = cgb.read8(br.SCREEN_INDEX)
        for _ in range(1 + len(episode_screens)):
            drive(0x80, lambda: cgb.read8(br.GAME_MODE) == br.MODE_PLAYING or cgb.read8(br.SCREEN_INDEX) != shown,
                  "START was not accepted")
            if cgb.read8(br.GAME_MODE) == br.MODE_PLAYING:
                break
            shown = cgb.read8(br.SCREEN_INDEX)
            assert shown in episode_screens, shown
            drive(0, lambda: cgb.io[0x40] == 0x81 and cgb.pc == cgb.symbols["screen_wait_start"], "episode screen never displayed")
            capture(f"{name}_screen{shown}")
        else:
            raise AssertionError("the episode screens never ended")
        drive(0, lambda: cgb.pc == cgb.symbols["main_loop"], "the world never came back")
        cgb.button_provider = None; cgb.buttons = 0

    for index in range(first - 1, last):
        level = campaign[index]
        if "select_level" in cgb.symbols:
            assert cgb.read8(br.LEVEL_INDEX) == index, (index, cgb.read8(br.LEVEL_INDEX))
            assert (cgb.read8(br.LEVEL_BANK), cgb.read8(br.LEVEL_PAGE)) == br.level_location(index)
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
        if index + 1 < last:
            generation = cgb.read16(br.WALL_EPOCH)
            cross_screen(br.MODE_INTERMISSION, f"sector{index + 2}_intermission")
            assert cgb.read16(br.WALL_EPOCH) != generation
            assert not live8(br.LEVEL_COMPLETE) and live8(br.PLAYER_HEALTH) == 99

    completed_at=len(records)
    if restart:
        generation=cgb.read16(br.WALL_EPOCH)
        if "select_level" in cgb.symbols:
            # The last sector ends the campaign; the ending returns to the
            # title, and its START begins the next run from the first sector.
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
              "campaign_levels":len(campaign),"sector_range":[first, last],"sectors":sectors,
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
    parser.add_argument("--output-dir", type=Path, default=br.GAME_BUILD / "playthrough")
    parser.add_argument("--rom",type=Path);parser.add_argument("--symbols",type=Path)
    parser.add_argument("--restart",action="store_true")
    parser.add_argument("--snapshot-mode",choices=("check","record","none"),default="record")
    parser.add_argument("--sectors",help="play sectors A-B (1-based, inclusive) instead of the whole campaign; "
                                          "a start past 1 is entered with that sector's continue code")
    args=parser.parse_args()
    if bool(args.rom)!=bool(args.symbols):parser.error("Supply ROM and symbols together")
    sectors=None
    if args.sectors:
        first,_,last=args.sectors.partition("-")
        sectors=(int(first),int(last or first))
    run(args.output_dir,rom_path=args.rom,symbols_path=args.symbols,restart=args.restart,
        snapshot_mode=None if args.snapshot_mode=="none" else args.snapshot_mode,sectors=sectors)
