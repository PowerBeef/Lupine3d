"""Whole-actor capacity transactions and hardware Y-only selection."""
import random
import unittest
from test_render_experiments import variant
import build_rom as br
from playtest import read_block
from sm83emu import CGB


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.build=variant(COMPACT_STRIPS=1,SCANLINE_ADMISSION=1)

    def cpu(self):
        c=CGB(self.build[0],self.build[1]); c.write8(0xFF70,1); c.write8(br.FLASH,0)
        c.call_subroutine("clear_entity_oam_shadow")
        return c

    def test_ui_occupancy_includes_hidden_x(self):
        c=self.cpu()
        ys=[0,1,16,32,80,96,144,159,160]
        for i,y in enumerate(ys):
            c.write8(br.OAM_SHADOW+4*i,y); c.write8(br.OAM_SHADOW+4*i+1,0)
        c.call_subroutine("clear_entity_oam_shadow")
        expected=[sum(y-16<=line<y for y in ys) for line in range(144)]
        self.assertEqual(list(read_block(c,br.WORLD_SCANLINES,144)),expected)

    def test_preflight_random_capacity_against_independent_selection(self):
        c=self.cpu();rng=random.Random(66)
        for _ in range(300):
            count=rng.randrange(5); ys=[rng.randrange(1,160) for _ in range(count)]
            occupancy=[rng.randrange(11) for _ in range(144)]
            used=rng.randrange(17); tiles=rng.randrange(17)*2
            for i,v in enumerate(occupancy): c.write8(br.WORLD_SCANLINES+i,v)
            for i,y in enumerate(ys):
                for j,v in enumerate((y,rng.choice((0,80,168)),0,1,255)): c.write8(br.ADMISSION_RECORDS+i*5+j,v)
            c.write8(br.ADMISSION_COUNT,count);c.write8(br.ADMISSION_FAILED,0)
            c.write8(br.SENTINEL_OAM_USED,used);c.write8(br.MASK_TILE_COUNT,tiles)
            expected=used+count<=16 and tiles+2*count<=32 and all(
                occupancy[line]+sum(y-16<=line<y for y in ys)<=10 for line in range(144))
            before=read_block(c,br.WORLD_SCANLINES,144),read_block(c,br.MASK_TILES,512)
            c.call_subroutine("preflight_actor")
            self.assertEqual(bool(c.a),expected,(ys,used,tiles))
            self.assertEqual((read_block(c,br.WORLD_SCANLINES,144),read_block(c,br.MASK_TILES,512)),before)
            self.assertEqual(c.read8(br.SENTINEL_OAM_USED),used);self.assertEqual(c.read8(br.MASK_TILE_COUNT),tiles)

    def actor(self,c,used,tiles):
        c.write8(br.SENTINEL_LOD,0);c.write8(br.SENTINEL_SCREEN_X,80);c.write8(br.ENTITY_FOOT_Y,96)
        c.write8(br.ENTITY_SCREEN_LEFT,255);c.write8(br.ENTITY_SCREEN_RIGHT,255)
        c.write8(br.SENTINEL_DEPTH,20)
        for i in range(80): c.write8(br.RAY_DEPTH+i,100)
        c.write8(br.SENTINEL_OAM_USED,used);c.write8(br.MASK_TILE_COUNT,tiles)
        c.write8(br.ENTITY_OAM_PTR_L,(br.OAM_SHADOW+br.ENTITY_OAM_FIRST*4+used*4)&255)
        c.write8(br.ENTITY_OAM_PTR_H,(br.OAM_SHADOW+br.ENTITY_OAM_FIRST*4+used*4)>>8)
        c.call_subroutine("render_actor_atomic")

    def test_fallback_commit_and_total_failure_are_atomic(self):
        for used,tiles,admitted in ((0,0,4),(14,28,2),(15,30,1),(16,32,0),(0,32,0)):
            c=self.cpu(); before=read_block(c,br.MASK_TILES,512),read_block(c,br.WORLD_SCANLINES,144)
            self.actor(c,used,tiles)
            self.assertEqual(c.read8(br.SENTINEL_OAM_USED),used+admitted,(used,tiles))
            self.assertEqual(c.read8(br.MASK_TILE_COUNT),tiles+admitted*2)
            self.assertEqual(c.read8(br.SENTINEL_LOD),0) # temporary fallback does not alter distance choice
            self.assertEqual(c.read8(br.LOD_HISTORY),0)
            if not admitted: self.assertEqual((read_block(c,br.MASK_TILES,512),read_block(c,br.WORLD_SCANLINES,144)),before)
            self.assertEqual(c.read8(br.ADMISSION_MODE),0);self.assertEqual(c.rom_bank,1)


if __name__=="__main__": unittest.main()


def default_build():
    """The production (slim, Sable art) ROM, built in a fresh process."""
    import json, os, subprocess, sys, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        env = {k: v for k, v in os.environ.items() if not k.startswith("LUPINE3D_")}
        env["LUPINE3D_POPULATION"] = "evidence"
        subprocess.run([sys.executable, "-c", "import sys,json;from pathlib import Path;"
                        "sys.path.insert(0,'tools');import build_rom as b;"
                        "r,a,m=b.make_rom();p=Path(sys.argv[1]);"
                        "(p/'rom').write_bytes(r);(p/'labels').write_text(json.dumps(a.labels))", folder],
                       cwd=br.ROOT, env=env, check=True, capture_output=True)
        return (Path(folder) / "rom").read_bytes(), json.loads((Path(folder) / "labels").read_text())


class WindowedPreflightTests(unittest.TestCase):
    """The production preflight checks only the lines its staged strips
    cover. Every submitter refuses at four world objects a line, so the
    other lines always pass: the decision must be the full scan's."""
    @classmethod
    def setUpClass(cls): cls.build = default_build()

    def test_windowed_decision_equals_the_full_scan(self):
        c = CGB(*self.build); c.write8(0xFF70, 1)
        rng = random.Random(1812)
        for case in range(1500):
            count = rng.randrange(5); ys = [rng.choice((rng.randrange(1, 160), 1, 16, 17, 143, 144, 159)) for _ in range(count)]
            occupancy = [rng.choice((0, 0, 1, 2, 3, 4, 4)) for _ in range(144)]
            used = rng.randrange(17); tiles = rng.randrange(17) * 2
            for i, v in enumerate(occupancy): c.write8(br.WORLD_SCANLINES + i, v)
            for i, y in enumerate(ys):
                for j, v in enumerate((y, rng.choice((0, 80, 168)), 0, 1, 255)): c.write8(br.ADMISSION_RECORDS + i * 5 + j, v)
            c.write8(br.ADMISSION_COUNT, count); c.write8(br.ADMISSION_FAILED, 0)
            c.write8(br.SENTINEL_OAM_USED, used); c.write8(br.MASK_TILE_COUNT, tiles)
            expected = used + count <= 16 and tiles + 2 * count <= 32 and all(
                occupancy[line] + sum(y - 16 <= line < y for y in ys) <= 4 for line in range(144))
            before = read_block(c, br.WORLD_SCANLINES, 144), read_block(c, br.ADMISSION_RECORDS, 20)
            c.call_subroutine("preflight_actor")
            self.assertEqual(bool(c.a), expected, (case, ys, used, tiles))
            self.assertEqual((read_block(c, br.WORLD_SCANLINES, 144), read_block(c, br.ADMISSION_RECORDS, 20)), before)
