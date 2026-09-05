"""Emitted fractional transforms against independently rounded integer math."""
import math
import random
import unittest
from test_render_experiments import variant
import build_rom as br
from sm83emu import CGB


def signed16(c,address):
    return int.from_bytes(bytes(c.read8(address+i) for i in range(2)),"little",signed=True)


def put16(c,address,value):
    for i,b in enumerate((value & 65535).to_bytes(2,"little")): c.write8(address+i,b)


def reference(dx,dy,yaw):
    cosine=round(math.cos(yaw*math.tau/256)*16384)
    sine=round(math.sin(yaw*math.tau/256)*16384)
    forward=(dx*cosine+dy*sine+8192)//16384
    lateral=(-dx*sine+dy*cosine+8192)//16384
    if not (-2048<=dx<2048 and -2048<=dy<2048 and 80<=forward<2048 and abs(lateral)<2048):
        return forward,lateral,None
    offset=(abs(lateral)*br.CAMERA_FOCAL_PIXELS+forward//2)//forward
    if offset>=88: return forward,lateral,None
    screen=(80+(-offset if lateral<0 else offset))&255
    foot=min(96,48+(7680+forward//2)//forward)+16
    depth=min(255,(forward+4)//8)
    return forward,lateral,(screen,foot,depth)


class ActorPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.variant=variant(COMPACT_STRIPS=1,ACTOR_PRECISION=1)

    def cpu(self):
        c=CGB(self.variant[0],self.variant[1]); c.write8(0xFF70,1)
        c.write8(br.DECAL_PROJECTING,1)
        for p in (br.PLAYER_XL,br.PLAYER_YL): put16(c,p,2048)
        return c

    def test_signed_products_and_single_rounding(self):
        c=self.cpu(); rng=random.Random(466097)
        for x,y in [(x,y) for x in (-2048,-1,0,1,2047) for y in (-16384,-1,0,1,16384)]+[(rng.randrange(-2048,2048),rng.randrange(-16384,16385)) for _ in range(200)]:
            c.hl=x&65535;c.de=y&65535;c.call_subroutine("actor_product_signed")
            actual=int.from_bytes(bytes(c.read8(br.Q14_PRODUCT+i) for i in range(4)),"little",signed=True)
            self.assertEqual(actual,x*y,(x,y)); self.assertEqual(c.rom_bank,1)

    def test_all_yaws_fractional_positions_and_live_world_bank(self):
        c=self.cpu(); rng=random.Random(508)
        cases=[(yaw,round(math.cos(yaw*math.tau/256)*f)-l,round(math.sin(yaw*math.tau/256)*f)+l)
               for yaw in range(256) for f,l in ((80,0),(81,1),(447,-7),(448,7),(575,-1),(960,13),(1088,0),(2047,-1))]
        cases += [(rng.randrange(256),rng.randrange(-2048,2048),rng.randrange(-2048,2048)) for _ in range(256)]
        for yaw,dx,dy in cases:
            for bank in (1,2) if yaw in (0,63,64,127,128,191,192,255) else (1,):
                c.write8(0xFF70,bank); c.write8(br.DECAL_PROJECTING,1)
                for p in (br.PLAYER_XL,br.PLAYER_YL): put16(c,p,2048)
                put16(c,br.ENTITY_WORLD_XL,2048+dx);put16(c,br.ENTITY_WORLD_YL,2048+dy);c.write8(br.ANGLE,yaw)
                c.call_subroutine("project_entity")
                forward,lateral,projected=reference(dx,dy,yaw)
                if -2048<=dx<2048 and -2048<=dy<2048:
                    self.assertEqual(signed16(c,br.ACTOR_FORWARD_Q8),forward,(yaw,dx,dy))
                    self.assertEqual(signed16(c,br.ACTOR_LATERAL_Q8),lateral,(yaw,dx,dy))
                self.assertEqual(bool(c.read8(br.SENTINEL_VISIBLE)),projected is not None,(yaw,dx,dy,projected))
                if projected:
                    self.assertEqual(tuple(c.read8(p) for p in (br.SENTINEL_SCREEN_X,br.ENTITY_FOOT_Y,br.SENTINEL_DEPTH)),projected,(yaw,dx,dy))
                self.assertEqual(c.rom_bank,1);self.assertEqual(c.io[0x70]&7,bank)

    def test_fractional_motion_reduces_projection_error(self):
        c=self.cpu(); errors={"q8":[],"q4":[]}
        for y in range(-128,129):
            put16(c,br.ENTITY_WORLD_XL,2048+481);put16(c,br.ENTITY_WORLD_YL,2048+y);c.write8(br.ANGLE,0)
            exact=80+y*br.CAMERA_FOCAL_PIXELS/481
            for mode,label in (("q8","project_entity"),("q4","project_entity_q4_reference")):
                c.call_subroutine(label);errors[mode].append(abs(c.read8(br.SENTINEL_SCREEN_X)-exact))
        self.assertLess(sum(errors["q8"]),sum(errors["q4"])/2)
        self.assertLessEqual(max(errors["q8"]),0.5)


if __name__=="__main__": unittest.main()
