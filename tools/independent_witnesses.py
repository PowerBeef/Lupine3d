#!/usr/bin/env python3
"""Frozen world images through pinned SameBoy CGB-0/E and mGBA adapters.

Scene writes are explicit diagnostics at main_loop, before the measured scene.
The core libraries are unmodified. Reports bind ROM, scene patches and pixels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image
import build_rom as br
from quality_witnesses import scene_corpus,setup,capture
from sm83emu import CGB


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sameboy',type=Path,default=br.BUILD/'sameboy_smoke')
    p.add_argument('--mgba',type=Path,default=br.BUILD/'mgba_smoke')
    p.add_argument('--output-dir',type=Path,default=br.BUILD/'independent-witnesses')
    p.add_argument('--scene',action='append');args=p.parse_args()
    provenance={}
    for core,executable,pinned in (("SameBoy",args.sameboy,"213a12ce93d66b105a113debd9396306066a7cfc"),
                                   ("mGBA",args.mgba,"507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6")):
        entry=json.loads(executable.with_suffix('.provenance.json').read_text())
        if entry['adapter_sha256']!=sha(executable.read_bytes()) or entry['core_commit']!=pinned:
            raise SystemExit(f"Rebuild {core} adapter with its pinned verification command")
        provenance[core]=entry
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    rom,asm,manifest=br.make_rom();rom_path=out/'candidate.gb';rom_path.write_bytes(rom)
    rows=[]
    for scene in scene_corpus():
        if args.scene and scene.name not in args.scene:continue
        c=CGB(rom,asm.labels);c.run(until_pc=asm.labels['main_loop']);writes=[];original=c.write8
        def write(address,value):
            if 0xC000<=address<0xE000 or 0xFF80<=address<0xFFFF:
                bank=(c.io[0x70]&7) or 1 if 0xD000<=address<0xE000 else 0
                writes.append(bytes((bank,address&255,address>>8,value&255)))
            original(address,value)
        c.write8=write;setup(c,scene);c.write8=original
        # set_test_world_byte also updates the isolated live bank directly.
        # Serialize the complete authored copy spans for BOTH banks, including
        # zero fields, so diagnostic setup is independent of power-on RAM.
        for bank in (1,2):
            for address,count in br.WORLD_COPY_RANGES:
                if 0xD000<=address<0xE000:
                    for offset in range(count):
                        target=address+offset
                        writes.append(bytes((bank,target&255,target>>8,c.wramx[bank][target-0xD000])))
        payload=asm.labels['main_loop'].to_bytes(2,'little')+len(writes).to_bytes(2,'little')+b''.join(writes)
        patch=out/(scene.name+'.bin');patch.write_bytes(payload)
        _,expected,_=capture(rom,asm.labels,scene);expected.save(out/(scene.name+'-host.png'))
        row=dict(scene=scene.name,patch_sha256=sha(payload),expected_rgb_sha256=sha(expected.tobytes()),cores={})
        for name,command in (('sameboy-cgb0',[str(args.sameboy.resolve()),str(rom_path.resolve()),str((out/(scene.name+'-cgb0')).resolve()),'200',str(patch.resolve())]),
                             ('sameboy-cgbe',[str(args.sameboy.resolve()),str(rom_path.resolve()),str((out/(scene.name+'-cgbe')).resolve()),'205',str(patch.resolve())]),
                             ('mgba',[str(args.mgba.resolve()),str(rom_path.resolve()),str((out/(scene.name+'-mgba')).resolve()),str(patch.resolve())])):
            result=subprocess.run(command,text=True,capture_output=True)
            if not result.stdout.strip():raise RuntimeError((name,scene.name,result.returncode,result.stderr))
            core=json.loads(result.stdout.strip().splitlines()[-1]);result.check_returncode()
            image=Image.open(command[2]+'_scene.ppm');image.save(command[2]+'.png')
            core['rgb_sha256']=sha(image.tobytes());core['rgb_matches_host']=image.tobytes()==expected.tobytes()
            core['passed']=core['passed'] and core['rgb_matches_host'];row['cores'][name]=core
        rows.append(row)
        report=dict(schema='lupine3d.independent-witnesses.v1',rom_sha256=manifest['sha256'],configuration_id=manifest['configuration_id'],
            cores=provenance,
            diagnostic_ram_writes=True,hardware_tested=False,scenes=rows,passed=all(v['passed'] for r in rows for v in r['cores'].values()))
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(scene.name,all(v['passed'] for v in row['cores'].values()),flush=True)
    if not rows:p.error('No selected scenes')
    if not report['passed']:raise SystemExit('Independent scene differences; review captures')


if __name__=='__main__':main()
