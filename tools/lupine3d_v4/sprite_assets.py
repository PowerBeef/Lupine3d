"""Deterministic native PNG validation and 2bpp compilation (no generation)."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]/'assets/sable_v2'

@lru_cache(maxsize=1)
def manifest():
    data=json.loads((ROOT/'assets.json').read_text())
    if data['schema']!='sable.native.v1':raise ValueError('unsupported native asset schema')
    return data

@lru_cache(maxsize=None)
def frames(name):
    record=manifest()['assets'][name];path=ROOT/record['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError(f'{name}: asset hash mismatch')
    im=Image.open(path);w,h=record['size'];n=len(record['frames'])
    if im.mode!='P' or im.size!=(w*n,h) or im.info.get('transparency')!=0:raise ValueError(f'{name}: indexed dimensions/transparency')
    if set(im.getdata())-set(range(4)):raise ValueError(f'{name}: exceeds 2bpp palette')
    if im.getpalette()[:12]!=[c for rgb in record['palette'] for c in rgb]:raise ValueError(f'{name}: palette differs')
    return tuple(tuple(tuple(im.getpixel((f*w+x,y)) for x in range(w)) for y in range(h)) for f in range(n))

def compile_frame(name,index,paired=False,column_major=False):
    px=frames(name)[index];w,h=len(px[0]),len(px);out=bytearray()
    coordinates=[(x,y) for y in range(0,h,8) for x in range(0,w,8)]
    if paired: coordinates=[(x,y+dy) for y in range(0,h,16) for x in range(0,w,8) for dy in (0,8)]
    if column_major:coordinates=[(x,y) for x in range(0,w,8) for y in range(0,h,8)]
    for x,y in coordinates:
        for row in px[y:y+8]:
            for bit in (0,1):out.append(sum(((row[x+i]>>bit)&1)<<(7-i) for i in range(8)))
    return bytes(out)

def compile_sheet(name,**kwargs):return b''.join(compile_frame(name,i,**kwargs) for i in range(len(frames(name))))

def evidence():
    for name in manifest()['assets']:frames(name)
    return {'schema':'sable.native.v1','sha256':hashlib.sha256((ROOT/'assets.json').read_bytes()).hexdigest(),
            'assets':{name:r['sha256'] for name,r in manifest()['assets'].items()}}
