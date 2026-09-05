"""Fixed near-plane experiment, independent rational projection comparisons."""
from fractions import Fraction
import math
import random
import unittest
from test_render_experiments import variant
import build_rom as br
from lupine3d_v4.precision import q14_direction
from sm83emu import CGB


def half_up(x): return (x.numerator*2+x.denominator)//(2*x.denominator)


class NearFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.build=variant(COMPACT_STRIPS=1,NEAR_FIELD=1)

    def test_emitted_candidate_against_rational_planes(self):
        c=CGB(self.build[0],self.build[1]);c.write8(0xFF70,1)
        rng=random.Random(707);focal=80/math.tan(math.radians(br.FOV_DEGREES/2))
        cases=[(yaw,record,distance,axis) for yaw in (0,1,63,64,65,127,128,191,192,254,255)
               for record in (0,39,79,80,159,239,240) for distance in (0,1,79,127,159,160,255,256,447,511,512,640) for axis in (0,1)]
        for yaw,record,distance,axis in cases:
            component=abs(q14_direction(yaw,record)[axis]);x=2*record+1 if record<80 else record-80+.5 if record<240 else 80
            correction=round(16384/math.sqrt(1+((x-80)/focal)**2))
            old_top,old_depth=(31,63) if distance<512 else (35,64)
            c.write8(br.ANGLE,yaw);c.write8(br.Q14_RECORD,record);c.write8(br.Q14_LOADED,0);c.write8(br.DDA_AXIS,axis)
            c.write8(br.DDA_DIST_L,distance&255);c.write8(br.DDA_DIST_H,distance>>8)
            c.write8(br.TOP_RESULT,old_top);c.write8(br.DEPTH_RESULT,old_depth)
            c.call_subroutine("refine_near_projection")
            expected=(old_top,old_depth)
            if component and old_depth<64:
                perpendicular=half_up(Fraction(distance*correction,component))
                if perpendicular<512:
                    expected=(48-min(48,half_up(Fraction(7680,max(1,perpendicular)))),half_up(Fraction(perpendicular,8)))
            self.assertEqual((c.read8(br.TOP_RESULT),c.read8(br.DEPTH_RESULT)),expected,(yaw,record,distance,axis))
            self.assertEqual(c.rom_bank,1)
        # Raw vector queries do not have normalized Q14 camera semantics.
        c.write8(br.Q14_RECORD,255);c.write8(br.TOP_RESULT,13);c.write8(br.DEPTH_RESULT,20)
        c.call_subroutine("refine_near_projection");self.assertEqual((c.read8(br.TOP_RESULT),c.read8(br.DEPTH_RESULT)),(13,20))

    def test_targeted_error_improves_without_far_field_change(self):
        c=CGB(self.build[0],self.build[1]);c.write8(0xFF70,1)
        errors=[0.,0.];changes=[[],[]]
        table=br.make_projection_top_lut();index=(127*18+17)*1024
        for distance in range(160,640):
            d32=(distance+4)//8;oldtop,olddepth=table[index+d32*2:index+d32*2+2]
            c.write8(br.ANGLE,0);c.write8(br.Q14_RECORD,240);c.write8(br.Q14_LOADED,0);c.write8(br.DDA_AXIS,0)
            c.write8(br.DDA_DIST_L,distance&255);c.write8(br.DDA_DIST_H,distance>>8)
            c.write8(br.TOP_RESULT,oldtop);c.write8(br.DEPTH_RESULT,olddepth);c.call_subroutine("refine_near_projection")
            newtop=c.read8(br.TOP_RESULT)
            if olddepth>=64:self.assertEqual((newtop,c.read8(br.DEPTH_RESULT)),(oldtop,olddepth))
            else:
                exact=max(0,48-7680/distance)
                errors[0]+=abs(oldtop-exact);errors[1]+=abs(newtop-exact)
                changes[0].append(oldtop);changes[1].append(newtop)
        self.assertLess(errors[1],errors[0])
        for seq in changes:self.assertTrue(all(a<=b for a,b in zip(seq,seq[1:])))


if __name__=="__main__":unittest.main()
