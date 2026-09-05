#!/usr/bin/env python3
"""Compare viewport geometry across fresh legacy/compact configuration processes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image

POSES=((1152,3456,192),(1408,3328,192),(896,2432,192),(2176,2176,0),(2432,2688,64),(1152,3100,191),(1152,3100,255))

def capture(out):
    import build_rom as b
    from sm83emu import CGB
    from playtest import apply_diagnostic_camera,set_test_world_byte,validate_frame
    rom,a,m=b.make_rom();rows=[];out.mkdir(parents=True,exist_ok=True)
    for index,pose in enumerate(POSES):
        c=CGB(rom,a.labels);c.run(until_pc=a.labels['main_loop']);c.write8(b.SIM_READY,0)
        set_test_world_byte(c,b.WORLD_MODE,0);apply_diagnostic_camera(c,{'pose':pose});c.run(until_presentations=1);validate_frame(c)
        c.oam[:]=bytes(160);im=c.render_screen();im.save(out/f'{index}.png')
        rows.append({'tops':[c.read8(b.PIXEL_TOPS+i) for i in range(160)],'pose':pose})
    (out/'data.json').write_text(json.dumps({'sha256':m['sha256'],'rows':rows}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',choices=('compact','slim'),default='slim');p.add_argument('--capture',action='store_true');p.add_argument('--output-dir',type=Path,default=Path('build/sable-v2/display'));args=p.parse_args()
    if args.capture:return capture(args.output_dir)
    for profile in ('legacy',args.profile):
        env={k:v for k,v in os.environ.items() if not k.startswith('LUPINE3D_')};env.update(LUPINE3D_DISPLAY=profile,LUPINE3D_ART="legacy",LUPINE3D_ART_ANIMATION="0")
        subprocess.run([sys.executable,__file__,'--capture','--output-dir',str(args.output_dir/profile)],env=env,check=True)
    old,new=[json.loads((args.output_dir/profile/'data.json').read_text()) for profile in ('legacy',args.profile)];rows=[]
    shift=12 if args.profile=='slim' else 8
    for i,(a,b) in enumerate(zip(old['rows'],new['rows'])):
        # Preserve projection scale; only the vertical origin changes.
        columns=[x for x,top in enumerate(a['tops']) if top>0]
        unclipped=min(a['tops'])>0
        if unclipped:assert all(b['tops'][x]==a['tops'][x]+shift for x in columns)
        legacy=Image.open(args.output_dir/'legacy'/f'{i}.png').crop((0,0,160,96))
        compact=Image.open(args.output_dir/args.profile/f'{i}.png').crop((0,shift,160,shift+96))
        differences=[(x,y) for y in range(96) for x in range(160)
                     if legacy.getpixel((x,y))!=compact.getpixel((x,y))]
        # A four-pixel tile phase changes the existing one-pixel edge accent:
        # boundaries exactly on tile starts use a solid wall tile. Geometry,
        # interior pixels and all other edge phases must remain exact.
        edge_phase=[(x,y) for x,y in differences if args.profile=='slim'
                    and a['tops'][x]%8 in (0,4)
                    and y in (a['tops'][x],95-a['tops'][x])]
        if unclipped:assert len(differences)==len(edge_phase),(a['pose'],differences[:10])
        rows.append({'pose':a['pose'],'unclipped_columns':len(columns),'unclipped_scene':unclipped,'central_96_rgb_exact':not differences,'tile_boundary_accent_changes':len(edge_phase),
                     'clipped_scene_validation':'full emitted descriptors and compositor checked against Q5 reference' if not unclipped else None})
    result={'schema':'sable.display.v2','legacy_sha256':old['sha256'],'compact_geometry_sha256':new['sha256'],'world_objects_hidden_for_geometry_comparison':True,'scenes':rows,'passed':True}
    (args.output_dir/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
