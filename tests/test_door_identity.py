"""Touching doors keep distinct decoration even with identical material."""
import unittest
from test_render_experiments import variant
import build_rom as br
from sm83emu import CGB
from playtest import read_block


class DoorIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new=variant(COMPACT_STRIPS=1,DOOR_IDENTITY=1);cls.old=variant(COMPACT_STRIPS=1,DOOR_IDENTITY=0)

    def test_physical_identity_splits_same_material_runs(self):
        for changed in (br.PIXEL_SEGMENT,br.PIXEL_KEYS,br.PIXEL_ALONG):
            results=[]
            for rom,labels,_ in (self.old,self.new):
                c=CGB(rom,labels);c.write8(0xFF70,1)
                for x in range(160):
                    for base,v in ((br.PIXEL_TOPS,20),(br.PIXEL_STYLES,4 if 40<=x<60 else 0),
                                   (br.PIXEL_KEYS,0x66 if 40<=x<60 else 0x25),
                                   (br.PIXEL_SEGMENT,3 if 40<=x<60 else 1),(br.PIXEL_ALONG,4)):
                        c.write8(base+x,v)
                for x in range(50,60): c.write8(changed+x,c.read8(changed+x)+(0x80 if changed==br.PIXEL_KEYS else 1))
                c.call_subroutine("decorate_pixel_styles");results.append(read_block(c,br.PIXEL_STYLES,160))
            old,new=results
            self.assertEqual(new[49],br.CREASE_STYLE);self.assertEqual(new[50],br.CREASE_STYLE)
            self.assertEqual(new[44:46],bytes([br.DOOR_SPINE_STYLE]*2))
            self.assertEqual(new[54:56],bytes([br.DOOR_SPINE_STYLE]*2))
            self.assertNotEqual(old,new)


if __name__=="__main__":unittest.main()
