#!/usr/bin/env python3
"""ROM-driven animation preview; controller-only input after explicit scene setup."""
import hashlib
import json
from pathlib import Path
from PIL import Image
import build_rom as b
from sm83emu import CGB
from playtest import apply_diagnostic_camera,set_test_world_byte
from runtime_observer import LCD_CPU_CYCLES


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=b.BUILD/'sable-v2/motion');p.add_argument('--scene',choices=('weapon','combat'),default='weapon');args=p.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    rom,a,meta=b.make_rom();c=CGB(rom,a.labels);c.run(until_pc=a.labels['main_loop'])
    # Stage a close confrontation; subsequent firing/turning runs entirely
    # through LCD-indexed controller samples and accepted simulation ticks.
    if args.scene=='weapon':apply_diagnostic_camera(c,{'pose':[2176,2432,192]})
    else:
        from quality_witnesses import Scene,setup
        grid=bytes(1 if x in (0,8,15) or y in (0,15) else 0 for y in range(16) for x in range(16))
        setup(c,Scene('combat_preview',grid,(1024,1152,0),((1536,1152),)))
        c.write8(b.SIM_READY,1)
    first=c.frame_count;images=[];rows=[];last_cycle=c.cycles;previous=c.presentations
    def buttons(*_):
        tick=c.frame_count-first
        if args.scene=='combat':return 16 if tick in (30,60,90) else 0
        return (16 if tick in (60,85,110,135,160) else 0) | (1 if 220<=tick<255 else 0)
    c.button_provider=buttons
    while c.frame_count-first<300:
        c.step()
        if c.presentations==previous:continue
        previous=c.presentations;images.append(c.render_screen());rows.append({'cycles':c.cycles,'duration_ms':(c.cycles-last_cycle)*1000/8388608,'snapshot_tick':c.read16(b.FRAME_TICK),'weapon_tile':c.oam[2],'flash_y':c.oam[36],'health':c.read8(b.PLAYER_HEALTH),'actor_state':c.read8(b.SENTINEL_STATE),'pickup_active':c.read8(b.PICKUP_ACTIVE),'exit_active':c.read8(b.EXIT_ACTIVE)})
        last_cycle=c.cycles
    for i,row in enumerate(rows):
        end=rows[i+1]['cycles'] if i+1<len(rows) else c.cycles
        row['visible_duration_ms']=(end-row['cycles'])*1000/8388608
    for scale in (1,4):
        frames=[im.resize((160*scale,144*scale),Image.Resampling.NEAREST) for im in images]
        for name,durations in [('actual',[max(10,round(row['visible_duration_ms']/10)*10) for row in rows]),('inspection',[250]*len(rows))]:
            frames[0].save(out/f'{name}-{scale}x.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    (out/'report.json').write_text(json.dumps({'schema':'sable.motion-preview.v1','rom_sha256':meta['sha256'],'diagnostic_setup':True,'game_ram_writes_after_setup':0,'gif_timing_quantization_ms':10,'frames':rows},indent=2)+'\n')
    images[0].save(out/'first.png');images[-1].save(out/'last.png')

if __name__=='__main__':main()
