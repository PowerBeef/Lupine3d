"""Same-snapshot startup RGB comparison for a time-varying art profile.

The ordinary controller smoke remains unpatched. A separate adapter invocation
freezes simulation at main_loop before its first presentation for exact RGB.
"""
import subprocess
from PIL import Image
import build_rom as b
from sm83emu import CGB


def frozen_startup(executable,rom,prefix,model=None):
    expected,asm,_=b.make_rom();host=CGB(expected,asm.labels);host.run(until_pc=asm.labels['main_loop'])
    host.write8(b.SIM_READY,0);host.run(until_presentations=1)
    payload=asm.labels['main_loop'].to_bytes(2,'little')+bytes((1,0,0,b.SIM_READY&255,b.SIM_READY>>8,0))
    patch=prefix.with_suffix('.bin');patch.write_bytes(payload)
    command=[str(executable.resolve()),str(rom.resolve()),str(prefix.resolve())]
    if model is not None:command.append(model)
    result=subprocess.run(command+[str(patch.resolve())],capture_output=True,text=True,check=True)
    actual=Image.open(str(prefix)+'_scene.ppm');actual.save(str(prefix)+'.png')
    return actual.tobytes()==host.render_screen().tobytes()
