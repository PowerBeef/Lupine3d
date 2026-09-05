"""Preserve legacy regressions while testing the default Sable ROM separately."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CompactArtTests(unittest.TestCase):
    def test_production_defaults_and_legacy_escape_hatch(self):
        env={k:v for k,v in os.environ.items() if not k.startswith('LUPINE3D_')}
        code="""import sys
sys.path.insert(0,'tools')
from lupine3d_v4.configuration import resolve
r=resolve({})
assert (r['display'],r['art'],r['art_animation'])==('slim','sable-v2',True)
r=resolve({'LUPINE3D_DISPLAY':'legacy'})
assert (r['display'],r['art'],r['art_animation'])==('legacy','legacy',False)
for flags in ({'LUPINE3D_REPROJECTION':'1','LUPINE3D_DISPLAY':'compact'},
              {'LUPINE3D_ART':'legacy','LUPINE3D_ART_ANIMATION':'1'}):
    try: resolve(flags)
    except ValueError: pass
    else: raise AssertionError(flags)
"""
        subprocess.run([sys.executable,'-c',code],env=env,cwd=ROOT,check=True)

    def test_emitted_compact_art_contracts(self):
        env={k:v for k,v in os.environ.items() if not k.startswith('LUPINE3D_')}
        env.update(LUPINE3D_DISPLAY='slim',LUPINE3D_ART='sable-v2')
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(ROOT/'tools/check_sable.py'),'--output-dir',directory],env=env,capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_display_geometry_in_fresh_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(ROOT/'tools/check_display.py'),'--output-dir',directory],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
