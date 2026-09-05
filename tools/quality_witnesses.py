#!/usr/bin/env python3
"""Frozen complete worlds and an analytic plane-intersection visibility oracle.

The oracle enumerates grid faces and finite door panels with rational
intersections. It does not call the renderer's DDA, projection LUT, adaptive
reconstruction, or height-to-depth model. Legacy defects are characterized,
not blessed as geometric truth. All RAM writes are diagnostic setup.
"""
import argparse
from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import build_rom as br
from playtest import apply_diagnostic_camera, set_test_world_byte, make_contact_sheet
from sm83emu import CGB


@dataclass(frozen=True)
class Scene:
    name: str
    grid: bytes
    pose: tuple[int, int, int]
    actors: tuple[tuple[int, int], ...]
    doors: tuple[tuple[int, int, int, int], ...] = ()  # x,y,orientation,aperture
    art_frame: int = -1


def scene_corpus():
    grid = bytes(1 if x in (0, 8, 15) or y in (0, 15) else 0 for y in range(16) for x in range(16))
    base = Scene("height_class_occlusion", grid, (1024,1152,0), ((1984,1152),))
    result = [base]
    corner = bytearray(grid); corner[5*16+6] = 1
    result.append(replace(base, name="actor_covered_discontinuity", grid=bytes(corner), actors=((1984,1312),)))
    thin = bytearray(grid); thin[4*16+6] = 1
    result.append(replace(base, name="thin_occluder", grid=bytes(thin)))
    result.append(replace(base, name="close_clipped_wall", pose=(2008,1152,0), actors=((2028,1152),)))
    result.append(replace(base, name="shallow_angle", pose=(1024,1152,62), actors=((1088,1984),)))
    door_grid = bytearray(grid); door_grid[4*16+6] = 3
    for aperture in (0, 64, 128, 192, 224):
        result.append(replace(base, name=f"finite_door_{aperture}", grid=bytes(door_grid), doors=((6,4,0,aperture),)))
    door_grid[5*16+6] = 3
    for second_axis in (0, 1):
        result.append(replace(base, name=f"touching_doors_axis_{second_axis}", grid=bytes(door_grid),
                              pose=(1024,1280,0), actors=((1984,1280),),
                              doors=((6,4,0,64),(6,5,second_axis,192))))
    for fraction in range(16):
        result.append(replace(base,name=f"fractional_actor_{fraction:02}",actors=((1984+fraction,1152+fraction),)))
    for yaw in (254,255,0,1,2):
        result.append(replace(base,name=f"yaw_wrap_{yaw:03}",pose=(1024,1152,yaw)))
    for distance in (64,79,80,81,95,96,447,448,449,575,576,959,960,1087,1088,1089):
        result.append(replace(base,name=f"near_lod_{distance:04}",actors=((1024+distance,1152),)))
    result.append(replace(base,name="two_actor_corner",grid=bytes(corner),actors=((1984,1408),(1904,1312))))
    result.append(replace(base,name="four_actor_coverage",actors=((1184,1056),(1200,1120),(1200,1184),(1184,1248))))
    if br.SABLE_ART:
        for size,distance in (('near',320),('mid',720),('far',1120)):
            for frame in range(12):
                result.append(replace(base,name=f'sable_{size}_{frame:02}',actors=((1024+distance,1152),),art_frame=frame))
    return result


def camera_basis(yaw):
    angle = yaw * math.tau / 256
    return round(math.cos(angle)*16384), round(math.sin(angle)*16384)


def physical_direction(yaw, column):
    focal = 80 / math.tan(math.radians(br.FOV_DEGREES / 2))
    angle = yaw * math.tau / 256 + math.atan((column+.5-80)/focal)
    return round(math.cos(angle)*16384), round(math.sin(angle)*16384)


def plane_hit(scene, column):
    px,py,yaw = scene.pose
    dx,dy = physical_direction(yaw,column)
    hits = []
    # At a common vertex the engine convention enters X before Y. Face
    # enumeration encodes that ordering explicitly, without a DDA recurrence.
    for axis, origin, normal, parallel_origin, parallel in ((0,px,dx,py,dy),(1,py,dy,px,dx)):
        if not normal: continue
        for plane in range(17):
            t = Fraction(plane*256-origin,normal)
            if t < 0: continue
            coordinate = Fraction(parallel_origin) + t*parallel
            along = coordinate // 256
            if coordinate % 256 == 0:
                if axis == 0 and parallel > 0 and t > 0: along -= 1
                if axis == 1 and parallel < 0: along -= 1
            cell = plane if normal > 0 else plane-1
            x,y = (cell,along) if axis == 0 else (along,cell)
            if not (0 <= x < 16 and 0 <= y < 16): continue
            material = scene.grid[y*16+x]
            if material and material != 3:
                hits.append((t,axis,x,y,material,Fraction(plane*256)))
    for x,y,axis,aperture in scene.doors:
        origin,normal,parallel_origin,parallel,cell,along = ((px,dx,py,dy,x,y) if axis == 0 else (py,dy,px,dx,y,x))
        if not normal: continue
        plane = cell*256+128
        t = Fraction(plane-origin,normal)
        coordinate = Fraction(parallel_origin)+t*parallel
        if t >= 0 and along*256+aperture <= coordinate < (along+1)*256:
            hits.append((t,axis,x,y,3,Fraction(plane)))
    if not hits: raise AssertionError((scene.name,column,"unbounded world"))
    t,axis,x,y,material,plane = min(hits)
    cx,cy = camera_basis(yaw)
    return dict(axis=axis,cell=(x,y),material=material,plane_q8=plane,
                ray_parameter=t,depth_q8=t*Fraction(dx*cx+dy*cy,16384))


def actor_transform(scene, actor):
    cx,cy = camera_basis(scene.pose[2])
    dx,dy = actor[0]-scene.pose[0], actor[1]-scene.pose[1]
    return Fraction(dx*cx+dy*cy,16384), Fraction(-dx*cy+dy*cx,16384)


def expected_mask(scene, actor, center):
    forward,_ = actor_transform(scene,actor)
    mask = 0
    for x in range(center-4,center+4):
        mask = (mask << 1) | int(0 <= x < 160 and forward > 0 and forward < plane_hit(scene,x)["depth_q8"])
    return mask


def setup(c, scene):
    c.write8(br.SIM_READY,0)
    apply_diagnostic_camera(c,dict(pose=list(scene.pose)))
    for offset,value in enumerate(scene.grid): set_test_world_byte(c,br.MAP+offset,value)
    for address,value in ((br.WORLD_MODE,1),(br.VRAM_PROFILE,br.VRAM_PROFILE_ENTITY),
                          (br.DOOR_COUNT,len(scene.doors)),(br.ACTOR_COUNT,len(scene.actors)),
                          (br.EXIT_ACTIVE,0),(br.LEVEL_COMPLETE,0)):
        set_test_world_byte(c,address,value)
    for index in range(br.MAX_DOORS):
        data = (bytes((*scene.doors[index][:3],0,1,scene.doors[index][3])) if index < len(scene.doors) else bytes(6))
        for offset,value in enumerate(data): set_test_world_byte(c,br.DOOR_TABLE+index*6+offset,value)
    for index in range(4):
        data = bytearray(16); data[4] = br.SENTINEL_DEAD
        if index < len(scene.actors):
            x,y = scene.actors[index]
            data[:6] = bytes((x&255,x>>8,y&255,y>>8,br.SENTINEL_DORMANT,3))
        for offset,value in enumerate(data): set_test_world_byte(c,br.ENTITY_SLOTS+index*16+offset,value)
        if index == 0:
            for offset,value in enumerate(data[:10]): set_test_world_byte(c,br.SENTINEL_XL+offset,value)
    if scene.art_frame >= 0:
        frame=scene.art_frame
        state=br.SENTINEL_DORMANT if frame<2 else br.SENTINEL_PATROL if frame<6 else br.SENTINEL_DEAD if frame>=9 else br.SENTINEL_ATTACK
        tick=32*frame if frame<2 else (frame-2)*8 if frame<6 else (frame-6)*4 if frame<8 else (frame-9)*12 if frame>=9 else 0
        reaction=1 if frame in (6,7) else 2 if frame==8 else 3 if frame>=9 else 0
        for address,value in ((br.SENTINEL_STATE,state),(br.ENTITY_SLOTS+4,state),(br.ENTITY_SLOTS+14,reaction),
                              (br.ACTOR_REACTION,reaction),(br.PICKUP_ACTIVE,int(frame>=9)),(br.ENTITY_SLOTS+10,int(frame>=9)),
                              (br.ACTOR_REACTION_TICK,0),(br.ACTOR_REACTION_TICK+1,0)):
            set_test_world_byte(c,address,value)
        c.write16(br.SIM_TICK,tick)
        c.write16(br.FRAME_TICK,tick)
    c.write8(br.WALL_CACHE_VALID,0)


def capture(rom, labels, scene):
    c = CGB(rom,labels); c.run(until_pc=labels["main_loop"])
    setup(c,scene)
    c.run(until_presentations=c.presentations+1)
    assert c.commit_events[-1]["vblank_safe"]
    image = c.render_screen()
    c.ime = False
    c.call_subroutine("project_sentinel")
    center = c.read8(br.SENTINEL_SCREEN_X)
    c.a = center; c.call_subroutine("entity_column_visible")
    actual = c.a
    expected = expected_mask(scene,scene.actors[0],center) if 0 <= center < 160 else 0
    return c,image,dict(name=scene.name,pose=scene.pose,actors=scene.actors,doors=scene.doors,
                        map_sha256=hashlib.sha256(scene.grid).hexdigest(),
                        rgb_sha256=hashlib.sha256(image.tobytes()).hexdigest(),
                        center=center,observed_mask=actual,legacy_mask=actual if not br.PHYSICAL_DEPTH else None,geometric_mask=expected,
                        intentional_legacy_difference=actual != expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--scene",action="append")
    args = parser.parse_args()
    rom,asm,manifest = br.make_rom()
    version = 2 if any(br.RENDER_CONFIG[name] for name in ("physical_depth","actor_precision","scanline_admission","door_identity","near_field")) else 1
    if args.output_dir is None: args.output_dir = br.BUILD/f"quality-witnesses-v{version}"
    args.output_dir.mkdir(parents=True,exist_ok=True)
    rows,images = [],[]
    for scene in scene_corpus():
        if args.scene and scene.name not in args.scene: continue
        _,image,row = capture(rom,asm.labels,scene)
        image.save(args.output_dir/(scene.name+".png")); rows.append(row); images.append((scene.name,image))
    if not rows: parser.error("No matching scenes")
    report = dict(schema=f"lupine3d.quality-witnesses.v{version}",rom_sha256=manifest["sha256"],
                  configuration_id=manifest["configuration_id"],diagnostic_ram_writes=True,
                  oracle="rational face/panel intersection with Q14 ray and camera vectors",
                  classification="legacy characterization" if version==1 else "quality candidate; residual Q5/transform errors are measured separately",scenes=rows)
    (args.output_dir/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    make_contact_sheet(images,args.output_dir/"contact_sheet.png")
    print(f"Captured {len(rows)} frozen worlds at {args.output_dir}")


if __name__ == "__main__": main()
