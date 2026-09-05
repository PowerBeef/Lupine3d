"""Scalar hot paths and persistent-cache faults on the emitted SM83 code."""
import random
import unittest

from test_render_experiments import variant
import build_rom as br
from sm83emu import CGB
from playtest import read_block


class ScalarCacheExperiments(unittest.TestCase):
    mix = 0
    @classmethod
    def setUpClass(cls):
        cls.rom,cls.labels,cls.metadata = variant(COMPACT_STRIPS=1, FOLDED=1,
                                                 INCREMENTAL_CERTIFICATE=1,CAMERA_SETUP=1,DYNAMIC_TILE_CACHE=1,CACHE_KEY_MIX=cls.mix)

    def boot(self):
        c = CGB(self.rom,self.labels); c.run(until_pc=self.labels["main_loop"])
        c.ime = False; c.write8(br.SIM_READY,0)
        return c

    def test_certificate_carries_boundaries_raw_and_axial_probes(self):
        c = self.boot()
        rng = random.Random(466)
        cases = [(x,256-x,n) for x in range(257) for n in (0,1,15,31)]
        cases += [(rng.randrange(257),rng.randrange(257),rng.randrange(32)) for _ in range(128)]
        for nx,ny,crossings in cases:
            nx += crossings*256
            c.write16(br.DDA_NEXT_X_L,nx); c.write16(br.DDA_NEXT_Y_L,ny)
            c.call_subroutine("initialize_certificate")
            self.assertEqual(c.read16(br.CERTIFICATE_THRESHOLD),nx+ny)
            for error in (nx+ny-1,nx+ny,nx+ny+1,-nx-ny,-nx-ny-1):
                c.write16(br.DDA_ERR_L,error & 65535)
                c.write8(br.DDA_ABS_X,90); c.write8(br.DDA_ABS_Y,90); c.write8(br.Q14_RECORD,0)
                c.call_subroutine("q14_crossing_uncertain_prepared")
                self.assertEqual(c.a,int(abs(error)<=nx+ny),(nx,ny,error))
            c.write8(br.Q14_RECORD,255); c.call_subroutine("q14_crossing_uncertain")
            self.assertEqual(c.a,0)
        for x,y in ((0,127),(127,0),(0,0)):
            c.write8(br.Q14_RECORD,0); c.write8(br.DDA_ABS_X,x); c.write8(br.DDA_ABS_Y,y)
            c.call_subroutine("q14_crossing_uncertain_prepared"); self.assertEqual(c.a,1)

    def test_every_observed_coarse_crossing_retains_the_original_sum(self):
        c = self.boot(); observations = []
        def check(cpu):
            if cpu.read8(br.Q14_RECORD) != 255 and cpu.read8(br.DDA_ABS_X) and cpu.read8(br.DDA_ABS_Y):
                expected = cpu.read16(br.DDA_NEXT_X_L)+cpu.read16(br.DDA_NEXT_Y_L)
                self.assertEqual(cpu.read16(br.CERTIFICATE_THRESHOLD),expected)
                observations.append(expected)
        c.breakpoints[self.labels["q14_crossing_uncertain_prepared"]] = check
        for angle in range(0,256,7):
            c.write8(br.ANGLE,angle); c.call_subroutine("cast_all")
        self.assertGreater(len(observations),2000)

    def test_hoisted_camera_pages_and_public_loader_across_all_banks(self):
        c = self.boot()
        addresses = (br.DDA_ABS_X,br.DDA_ABS_Y,br.DDA_STEP_X,br.DDA_STEP_Y,
                     br.DDA_ANGLE_L,br.DDA_ANGLE_H,br.DDA_CORRECTION,
                     br.RAY_PROJECTION_X,br.RAY_PROJECTION_X+1,br.RAY_PROJECTION_Y,br.RAY_PROJECTION_Y+1,
                     br.Q14_X,br.Q14_X+1,br.Q14_Y,br.Q14_Y+1)
        for yaw in range(256):
            c.write8(br.ANGLE,yaw); c.call_subroutine("prepare_frame_boundaries")
            for record in (0,15,16,79,80,239,240):
                c.write8(br.Q14_RECORD,record); c.call_subroutine("load_ray_setup_prepared")
                where = br.RAY_SETUP_ROM_BANK*16384+(yaw*256+record)*16
                self.assertEqual(bytes(c.read8(address) for address in addresses),self.rom[where:where+15])
                self.assertEqual(c.rom_bank,1)
            c.write8(br.ANGLE,(yaw+1)&255); c.call_subroutine("load_ray_setup")
            self.assertEqual(c.read8(br.FRAME_SETUP_BANK),br.RAY_SETUP_ROM_BANK+((yaw+1)&255)//4)

    def test_cache_collision_replacement_generation_profile_and_irq(self):
        c = self.boot(); c.call_subroutine("clear_dynamic_cache")
        counts = {"hit":0,"miss":0}
        def count(kind):
            def visit(cpu): counts[kind] += 1
            return visit
        c.breakpoints[self.labels["dynamic_cache_hit"]] = count("hit")
        c.breakpoints[self.labels["dynamic_cache_miss"]] = count("miss")
        def compose(tops, *, cached=True):
            c.write16(br.SCAN_TOP_PTR_L,br.PIXEL_TOPS); c.write16(br.SCAN_STYLE_PTR_L,br.PIXEL_STYLES)
            c.write8(br.TILE_Y0,24); c.write8(br.DARK_MASK,0xAA); c.write8(br.SIGNATURE_HASH,17)
            for i,top in enumerate(tops): c.write8(br.PIXEL_TOPS+i,top); c.write8(br.PIXEL_STYLES+i,1 if i%2==0 else 0)
            c.write16(br.DYN_PTR_L,br.DYNAMIC_TILES)
            c.call_subroutine("compose_dynamic_tile_cached" if cached else "compose_dynamic_tile")
            self.assertEqual(c.read16(br.DYN_PTR_L),br.DYNAMIC_TILES+16)
            self.assertEqual(c.io[0x70]&7,1)
            return read_block(c,br.DYNAMIC_TILES,16)
        first,second = [26,27,28,29,30,31,32,33],[26,27,28,29,30,31,32,34]
        expected = compose(first,cached=False)
        self.assertEqual(compose(first),expected)
        self.assertEqual(counts,{"hit":0,"miss":1})
        self.assertEqual(compose(first),expected)
        self.assertEqual(counts,{"hit":1,"miss":1})
        expected_second = compose(second,cached=False)
        self.assertEqual(compose(second),expected_second)
        self.assertEqual(counts,{"hit":1,"miss":2})
        self.assertEqual(compose(first),expected)
        self.assertEqual(counts,{"hit":1,"miss":3})
        c.write8(br.VRAM_PROFILE,c.read8(br.VRAM_PROFILE)^1)
        self.assertEqual(compose(first),expected)
        self.assertEqual(counts["miss"],4)
        c.write16(br.WALL_EPOCH,65535); c.call_subroutine("invalidate_wall_cache")
        self.assertEqual(c.read16(br.WALL_EPOCH),0)
        self.assertTrue(all(c.wramx[3][i*32]==0 for i in range(128)))
        self.assertEqual(compose(first),expected)
        # Interrupt the full-key comparison while bank 3 is selected. The
        # ISR must leave the entry, fixed staging and renderer bank intact.
        def irq(cpu):
            cpu.write8(0xFF0F,1)
            del cpu.breakpoints[self.labels["dynamic_cache_compare"]]
        c.breakpoints[self.labels["dynamic_cache_compare"]] = irq
        c.ime=True; c.write8(0xFFFF,1)
        self.assertEqual(compose(first),expected)
        self.assertTrue(c.interrupt_events)
        c.call_subroutine("load_level")
        self.assertTrue(all(c.wramx[3][i*32]==0 for i in range(128)))

    def test_warm_cache_preserves_full_allocation_and_packets(self):
        c = self.boot(); c.call_subroutine("clear_dynamic_cache")
        c.call_subroutine("render_view")
        def packet():
            return (c.read8(br.DYN_COUNT), read_block(c,br.DYNAMIC_TILES,c.read8(br.DYN_COUNT)*16),
                    read_block(c,br.VIEW_MAP,384),read_block(c,br.VIEW_ATTRIBUTES,384))
        cold = packet(); c.call_subroutine("render_view")
        self.assertEqual(packet(),cold)
        self.assertEqual(c.io[0x70]&7,1)


class MixedCacheExperiments(ScalarCacheExperiments):
    mix = 1


if __name__ == "__main__": unittest.main()
