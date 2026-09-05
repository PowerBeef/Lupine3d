#!/usr/bin/env python3
"""Diagnostic build variants; never overwrites the default playable ROM."""
import argparse
import hashlib
import json
from pathlib import Path
import build_rom as br
from playtest import make_contact_sheet, oam_budget, set_test_world_byte, validate_frame
from sm83emu import CGB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=("reprojection", "two-actors", "folding"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rom, asm, _ = br.make_rom()
    c = CGB(rom, asm.labels); c.run(until_pc=asm.labels["main_loop"])
    c.ime = False; c.write8(br.SIM_READY, 0)
    images, checks = [], {}
    def pose(x, y, angle):
        for address, value in ((br.PLAYER_XL, x & 255), (br.PLAYER_XH, x >> 8),
                               (br.PLAYER_YL, y & 255), (br.PLAYER_YH, y >> 8), (br.ANGLE, angle)):
            set_test_world_byte(c, address, value)
    if args.variant == "folding":
        # Freeze simulation: a representation-only A/B must compare the same
        # world, even when its two implementations take different cycle counts.
        set_test_world_byte(c, br.WORLD_MODE, 0)
        for action in json.loads((br.ROOT / "playtests/coherence_tour.json").read_text())["actions"]:
            if "pose" in action: pose(*action["pose"])
            if "b" in action.get("buttons", []):
                c.call_subroutine("open_door"); c.wramx[2][:256] = c.wramx[1][:256]
            c.run(until_presentations=c.presentations + 1); validate_frame(c)
            if "capture" in action:
                image = c.render_screen(); images.append((action["capture"], image))
                checks[action["capture"]] = hashlib.sha256(image.tobytes()).hexdigest()
    elif args.variant == "two-actors":
        assert len(br.ACTIVE_LEVEL.entities) == 2
        pose(2176, 2432, 224); c.run(until_presentations=1); validate_frame(c)
        checks = oam_budget(c); checks["world_objects"] = c.read8(br.SENTINEL_OAM_USED)
        checks["actor_objects"] = sum((c.oam[(br.ENTITY_OAM_FIRST+i)*4+3] & 7) == 1
                                      for i in range(checks["world_objects"]))
        assert checks["actor_objects"] > 4 and checks["max_oam_per_scanline"] <= 10
        images.append(("two_sentinels", c.render_screen()))
    else:
        assert br.ENABLE_MICRO_REPROJECTION
        c.call_subroutine("clear_entity_oam_shadow")
        for i in range(4):
            c.b, c.c, c.d, c.e = 56 + 16 * (i // 2), 72 + 8 * (i % 2), i * 2, 1
            c.call_subroutine("submit_masked_oam")
        c.call_subroutine("wait_vblank")
        c.call_subroutine("upload_masked_tiles"); c.call_subroutine("publish_oam_packet")
        before = bytes(c.oam)
        for i in range(br.ENTITY_OAM_COUNT):
            c.write8(br.OAM_SHADOW + (br.ENTITY_OAM_FIRST + i) * 4 + 1, 199)
        c.write8(br.INPUT_LAST_RAW, 1)
        for _ in range(7):
            c.call_subroutine("wait_vblank"); c.call_subroutine("update_reprojection_vblank")
        assert c.read8(br.REPROJECT_OFFSET) == 4 and c.io[br.SCX & 255] == 4
        assert bytes(c.oam[:br.ENTITY_OAM_FIRST * 4]) == before[:br.ENTITY_OAM_FIRST * 4]
        for i in range(br.ENTITY_OAM_FIRST, br.ENTITY_OAM_FIRST + br.ENTITY_OAM_COUNT):
            assert c.oam[i * 4 + 1] == (before[i * 4 + 1] - 4) & 255
            assert c.oam[i * 4] == before[i * 4]
        c.call_subroutine("reset_reprojection_for_commit")
        assert c.read8(br.REPROJECT_OFFSET) == 0 and c.io[br.SCX & 255] == 0
        c.call_subroutine("populate_reprojection_guards"); c.call_subroutine("build_surface_attributes")
        for row in range(12):
            for address in (br.VIEW_MAP, br.VIEW_ATTRIBUTES):
                assert c.read8(address + row * 32 + 31) == c.read8(address + row * 32)
                assert c.read8(address + row * 32 + 20) == c.read8(address + row * 32 + 19)
        checks = dict(clamp_exact=True, ui_unchanged=True, published_world_x_exact=True,
                      future_shadow_ignored=True, tile_and_attribute_guards_exact=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if images: make_contact_sheet(images, args.output.with_suffix(".png"))
    report = dict(passed=True, variant=args.variant, rom_sha256=hashlib.sha256(rom).hexdigest(),
                  diagnostic_ram_injections=True, checks=checks)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
