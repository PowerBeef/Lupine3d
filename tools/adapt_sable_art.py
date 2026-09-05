#!/usr/bin/env python3
"""Offline, reproducible native adaptation. Never called by ROM builds.

Generated masters are design sources; cell crops, baselines, palette thresholds
and LOD cleanup below are deliberate native authoring decisions.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'assets/sable_v2'
PALETTES = {'sentinel': [(0,0,0),(39,28,32),(170,53,50),(238,218,175)],
            'shotgun': [(0,0,0),(30,35,40),(111,132,137),(238,229,197)],
            'helmet': [(0,0,0),(25,32,35),(89,129,126),(238,229,197)]}
NAMES = ['idle_a','idle_b','walk_left','walk_pass_a','walk_right','walk_pass_b',
         'attack_raise','attack_fire','hurt','death_kneel','death_fall','death_down']

def indexed(size, palette):
    im=Image.new('P',size); im.putpalette(sum(palette,()) if isinstance(palette[0],tuple) else palette)
    im.info['transparency']=0
    return im

def adapt(im, box, size, palette, height=None):
    crop=im.crop(box).convert('RGB')
    mask=Image.new('L',crop.size)
    mask.putdata([0 if r>120 and b>80 and r>g*1.5 and b>g*1.3 else 255 for r,g,b in crop.getdata()])
    bounds=mask.getbbox(); crop=crop.crop(bounds); mask=mask.crop(bounds)
    # Threshold after box filtering the source; final output has four indices
    # and binary coverage. It is not an antialiased runtime sprite.
    target=(size[0],height or size[1]); crop=crop.resize(target,Image.Resampling.BOX); mask=mask.resize(target,Image.Resampling.BOX)
    out=indexed(size,palette); pixels=[]
    for (r,g,b),a in zip(crop.getdata(),mask.getdata()):
        value=max(r,g,b)
        pixels.append(0 if a<128 else 3 if min(r,g,b)>145 else 2 if value>70 else 1)
    cel=indexed(target,palette);cel.putdata(pixels);out.paste(cel,(0,size[1]-target[1]))
    return out

def save_sheet(name, frames, palette, labels, ticks):
    w,h=frames[0].size;sheet=indexed((w*len(frames),h),palette)
    for i,frame in enumerate(frames):sheet.paste(frame,(i*w,0))
    path=ROOT/'native'/f'{name}.png';sheet.save(path,transparency=0,optimize=False)
    record={'file':f'native/{name}.png','size':[w,h],'frames':labels,'ticks':ticks,'anchor':[w//2,h],
            'palette':[list(c) for c in palette], 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    enlarged=sheet.resize((sheet.width*6,h*6),Image.Resampling.NEAREST).convert('RGBA')
    enlarged.save(ROOT/'previews'/f'{name}-sheet.png')
    for cadence,ms in [('inspection',240),('presentation',100)]:
        views=[f.convert('RGBA').resize((w*6,h*6),Image.Resampling.NEAREST) for f in frames]
        views[0].save(ROOT/'previews'/f'{name}-{cadence}.gif',save_all=True,append_images=views[1:],duration=ms,loop=0,disposal=2)
    return record

def main():
    for folder in ('native','previews'): (ROOT/folder).mkdir(exist_ok=True)
    records={};source=Image.open(ROOT/'masters/sentinel.png'); near=[]
    # Columns/rows are selected from the returned master, not assumed prompt dimensions.
    for i in range(12):
        x=i%4;y=i//4;box=(x*256,[130,550,1010][y],(x+1)*256,[485,915,1360][y])
        near.append(adapt(source,box,(16,32),PALETTES['sentinel'],(32 if i<9 else [27,20,10][i-9])))
    records['sentinel_near']=save_sheet('sentinel_near',near,PALETTES['sentinel'],NAMES,[32,32,8,8,8,8,4,4,8,12,12,12])
    for name,width in [('mid',16),('far',8)]:
        frames=[]
        for i,frame in enumerate(near):
            cel=frame.resize((width,16),Image.Resampling.NEAREST)
            # Explicit small-LOD silhouette edits: readable visor, respirator,
            # shoulder planes and a one-pixel gap between grounded legs.
            if i<9:
                for x in range(width//2-1,width//2+2):cel.putpixel((min(width-1,x),3),3)
                cel.putpixel((width//2,4),1)
                for y in (13,14,15):cel.putpixel((width//2,y),0)
                cel.putpixel((1,6),2);cel.putpixel((width-2,6),2)
            frames.append(cel)
        records['sentinel_'+name]=save_sheet('sentinel_'+name,frames,PALETTES['sentinel'],NAMES,records['sentinel_near']['ticks'])
    source=Image.open(ROOT/'masters/shotgun.png');frames=[]
    for i in range(5):frames.append(adapt(source,(i*280,380,min(source.width,(i+1)*280),810),(32,32),PALETTES['shotgun'],[27,32,30,28,27][i]))
    records['shotgun']=save_sheet('shotgun',frames,PALETTES['shotgun'],['idle','recoil','pump_back','pump_forward','recovery'],[0,4,6,6,8])
    source=Image.open(ROOT/'masters/helmet.png');frames=[adapt(source,(i*source.width//4,0,(i+1)*source.width//4,source.height),(16,16),PALETTES['helmet']) for i in range(4)]
    records['helmet']=save_sheet('helmet',frames,PALETTES['helmet'],['normal','blink','hurt','dead'],[0,4,8,0])
    for name,count in [('flash',2),('reticle',1)]:
        frames=[]
        for phase in range(count):
            f=indexed((8,16),PALETTES['shotgun'])
            for y in range(8):
                for x in range(8):
                    d=abs(x-3)+abs(y-3)
                    if name=='flash' and d<(5-phase) and (d<3 or (x+y+phase)%2):f.putpixel((x,y),3 if d<2 else 2)
                    if name=='reticle' and (x,y) in ((1,3),(2,3),(5,3),(6,3),(3,1),(3,2),(3,5),(3,6)):f.putpixel((x,y),3)
            frames.append(f)
        records[name]=save_sheet(name,frames,PALETTES['shotgun'],['a','b'][:count],[1]*count)
    from lupine3d_v4.artwork import compact_hud_pixels
    palette=[(16,24,32),(41,58,66),(238,230,197),(82,132,132)]
    panel=indexed((160,32),palette);panel.putdata([v for row in compact_hud_pixels() for v in row])
    records['hud']=save_sheet('hud',[panel],palette,['panel'],[0])
    slim=indexed((160,24),palette);slim.putdata([v for row in compact_hud_pixels(24) for v in row])
    records['hud_slim']=save_sheet('hud_slim',[slim],palette,['panel'],[0])
    from lupine3d_v4.steel_hud import PALETTE, panel_pixels, portrait_pixels
    panel=indexed((160,24),PALETTE)
    panel.putdata([v for row in panel_pixels() for v in row])
    records['hud_steel']=save_sheet('hud_steel',[panel],PALETTE,['panel'],[0])
    portraits=[]
    for pixels in portrait_pixels():
        cel=indexed((16,16),PALETTE);cel.putdata([v for row in pixels for v in row]);portraits.append(cel)
    records['helmet_steel']=save_sheet('helmet_steel',portraits,PALETTE,['normal','blink','hurt','dead'],[0,4,8,0])
    (ROOT/'assets.json').write_text(json.dumps({'schema':'sable.native.v1','assets':records,'preview_note':'Inspection 240 ms/cel; presentation preview 100 ms/cel is illustrative. ROM-driven previews record actual cadence.'},indent=2)+'\n')

if __name__=='__main__':main()
