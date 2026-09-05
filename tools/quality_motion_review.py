#!/usr/bin/env python3
"""Side-by-side slow motion of hash-bound frozen quality transitions."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    reports=[json.loads((folder/'report.json').read_text()) for folder in (args.before,args.after)]
    scenes=[r['scene'] for r in reports[0]['scenes']]
    evidence=[]
    for group,prefix in (('fractional-motion','fractional_actor_'),('yaw-wrap','yaw_wrap_'),('near-and-lod','near_lod_'),('door-aperture','finite_door_')):
        frames=[]
        for name in scenes:
            if not name.startswith(prefix):continue
            frame=Image.new('RGB',(640,312),(12,17,21));draw=ImageDraw.Draw(frame)
            for i,folder in enumerate((args.before,args.after)):
                src=Image.open(folder/(name+'-host.png')).convert('RGB')
                frame.paste(src.resize((320,288),Image.Resampling.NEAREST),(i*320,24))
            draw.text((8,6),'Performance reference',(220,230,235));draw.text((328,6),'Quality candidate',(220,230,235))
            frames.append(frame)
        path=args.output_dir/(group+'.gif');frames[0].save(path,save_all=True,append_images=frames[1:],duration=300,loop=0,disposal=2)
        evidence.append(dict(group=group,frames=len(frames),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (args.output_dir/'report.json').write_text(json.dumps(dict(schema='lupine3d.quality-motion.v1',
        before_rom_sha256=reports[0]['rom_sha256'],after_rom_sha256=reports[1]['rom_sha256'],
        diagnostic_snapshots=True,lcd_timed_gameplay=False,frame_duration_ms=300,groups=evidence),indent=2)+'\n')


if __name__=='__main__':main()
