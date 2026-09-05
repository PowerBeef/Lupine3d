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
        c.write8(br.ENTITY_OAM_PTR_L,(br.OAM_SHADOW+40+used*4)&255)
        c.write8(br.ENTITY_OAM_PTR_H,(br.OAM_SHADOW+40+used*4)>>8)
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
