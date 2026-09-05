#!/usr/bin/env python3
"""Compare HUD work and frozen world pixels against an archived slim ROM."""
import argparse
import hashlib
import json
from pathlib import Path

import build_rom as b
from playtest import apply_diagnostic_camera
from sm83emu import CGB, parse_symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-rom', type=Path, required=True)
    parser.add_argument('--baseline-symbols', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--expected-publication-delta-cycles', type=int, default=0,
                        help='Expected measured CPU T-cycle change; preparation must remain exact.')
    args = parser.parse_args()
    assert b.SLIM_DISPLAY and b.SABLE_ART
    rom, asm, manifest = b.make_rom()
    old = args.baseline_rom.read_bytes()
    lanes = ((old, parse_symbols(args.baseline_symbols)), (rom, asm.labels))

    def boot(data, labels):
        c = CGB(data, labels)
        c.run(until_pc=labels['main_loop'])
        c.write8(b.SIM_READY, 0)
        return c

    world = []
    for pose in ((1152,3456,192), (1408,3328,192), (1152,3136,192),
                 (1152,3100,191), (1152,3100,255), (1408,3200,0)):
        images = []
        for data, labels in lanes:
            c = boot(data, labels)
            apply_diagnostic_camera(c, {'pose': pose})
            c.run(until_presentations=2)
            images.append(c.render_screen())
        equal = images[0].crop((0,0,160,120)).tobytes() == images[1].crop((0,0,160,120)).tobytes()
        assert equal, pose
        world.append(dict(pose=pose, world_and_foreground_rgb_exact=equal))

    machines = [boot(*lane) for lane in lanes]
    for c in machines:
        c.ime = False
        c.write8(0xff40, 0)
    rows = []
    for health, hurt, tick, done in ((99,0,8,0), (99,0,0,0), (42,1,8,0),
                                   (0,0,8,0), (79,0,8,1)):
        costs = []
        for c in machines:
            c.write8(b.PLAYER_HEALTH, health)
            c.write8(b.HURT_ACTIVE, hurt)
            c.write16(b.FRAME_TICK, tick)
            c.write8(b.LEVEL_COMPLETE, done)
            measured = {}
            for entry in ('prepare_hud_tiles', 'update_hud_tiles'):
                start = c.cycles
                c.call_subroutine(entry)
                measured[entry] = c.cycles - start
            costs.append(measured)
        assert costs[0]['prepare_hud_tiles'] == costs[1]['prepare_hud_tiles'], costs
        assert costs[1]['update_hud_tiles']-costs[0]['update_hud_tiles'] == args.expected_publication_delta_cycles, costs
        rows.append(dict(state=[health,hurt,tick,done], baseline=costs[0], candidate=costs[1]))
    result = dict(schema='sable.hud-comparison.v2',
                  baseline_sha256=hashlib.sha256(old).hexdigest(),
                  candidate_sha256=manifest['sha256'],
                  timing_unit='cpu_t_cycles', diagnostic_setup=True,
                  expected_publication_delta_cycles=args.expected_publication_delta_cycles,
                  scope='HUD subroutine timing and frozen world RGB; live motion measured separately',
                  world=world, hud_work=rows, passed=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
