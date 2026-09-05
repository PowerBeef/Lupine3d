"""Exact padding and narrow contexts with real queued simulation work."""
import unittest

from test_render_experiments import variant
import build_rom as br
from playtest import read_block
from sm83emu import CGB
from lupine3d_v4.surfaces import surface_attributes


class SecondaryExperiments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = variant(COMPACT_STRIPS=1,FOLDED=1,ATTRIBUTE_PADDING=1,NARROW_YIELDS=1)
        cls.reference = variant(COMPACT_STRIPS=1,FOLDED=1,ATTRIBUTE_PADDING=0,NARROW_YIELDS=0)

    def boot(self, variant):
        c = CGB(variant[0],variant[1]); c.run(until_pc=variant[1]["main_loop"])
        c.ime=False; c.write8(br.SIM_READY,0)
        return c

    def test_padding_retains_all_384_attribute_bytes_on_both_pages(self):
        c = self.boot(self.candidate)
        for page in (0,1):
            for profiles in ([0]*160,[1]*160,[2]*160,[i%3 for i in range(160)],[(i//8)%3 for i in range(160)]):
                for i,p in enumerate(profiles): c.write8(br.PIXEL_SURFACE+i,p)
                c.write8(br.CURRENT_PAGE,page^1); c.call_subroutine("build_surface_attributes")
                self.assertEqual(read_block(c,br.VIEW_ATTRIBUTES,384),surface_attributes(profiles,page))

    def test_ray_and_column_contexts_preserve_snapshot_and_drain_the_same_queue(self):
        for entry in ("cast_all","render_view"):
            contexts = [self.boot(v) for v in (self.reference,self.candidate)]
            for c in contexts:
                c.write8(br.INPUT_QUEUE_TAIL,0); c.write8(br.INPUT_QUEUE_HEAD,4)
                for i,buttons in enumerate((5,21,32,0)):
                    for j,value in enumerate((i+1,0,buttons,buttons)):
                        c.write8(br.INPUT_QUEUE+i*4+j,value)
                c.write8(br.SIM_READY,1)
                snapshot = read_block(c,br.MAP,256)+read_block(c,br.PLAYER_XL,8)+read_block(c,br.ENTITY_SLOTS,65)
                c.call_subroutine(entry)
                self.assertEqual(snapshot,read_block(c,br.MAP,256)+read_block(c,br.PLAYER_XL,8)+read_block(c,br.ENTITY_SLOTS,65))
                self.assertEqual(c.read8(br.INPUT_QUEUE_TAIL),4)
                self.assertEqual(c.read16(br.SIM_TICK),4)
                self.assertEqual(c.io[0x70]&7,1)
            generic,narrow = contexts
            self.assertEqual(generic.wramx[2],narrow.wramx[2])
            for address,count in ((br.RAY_TOPS,160),(br.RAY_KEYS,160),(br.PIXEL_TOPS,640),
                                  (br.RAY_DEPTH,160),(br.PIXEL_SEGMENT,160),(br.RAY_SURFACE,80),
                                  (br.PIXEL_SURFACE,160),(br.VIEW_MAP,384),
                                  (br.DYNAMIC_TILES,generic.read8(br.DYN_COUNT)*16)):
                self.assertEqual(read_block(generic,address,count),read_block(narrow,address,count),(entry,hex(address)))
            for address in (br.ADAPTIVE_CASTS,br.EDGE_RECASTS,br.EVENT_COUNT,br.DYN_COUNT):
                self.assertEqual(generic.read8(address),narrow.read8(address))


if __name__ == "__main__": unittest.main()
