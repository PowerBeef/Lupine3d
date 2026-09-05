"""Four-anchor certificates, exact terminal records and bounded split storage."""
import unittest

from test_render_experiments import variant
import build_rom as br
from sm83emu import CGB
from playtest import read_block
from lupine3d_v4.precision import q14_direction
from lupine3d_v4.packets import PK_FIRST,PK_COUNT,PK_STACK,PK_NX,PK_NY,PK_EMIN,PK_EMAX


class PacketTests(unittest.TestCase):
    reuse = False
    @classmethod
    def setUpClass(cls):
        cls.packet = variant(COMPACT_STRIPS=1,FOLDED=1,ANCHOR_PACKETS=1,PACKET_BOUNDS_REUSE=int(cls.reuse))
        cls.scalar = variant(COMPACT_STRIPS=1,FOLDED=1,ANCHOR_PACKETS=0,PACKET_BOUNDS_REUSE=0)

    def boot(self,v):
        c = CGB(v[0],v[1]); c.run(until_pc=v[1]["main_loop"])
        c.ime=False; c.write8(br.SIM_READY,0)
        return c

    def test_padding_and_scalar_prepared_records_are_byte_exact(self):
        base = br.RAY_SETUP_ROM_BANK*16384
        for yaw in range(256):
            where = base+yaw*4096
            self.assertEqual(self.packet[0][where:where+241*16],self.scalar[0][where:where+241*16])
            self.assertEqual(self.packet[0][where+251*16:where+4096],bytes(5*16))
            for group in range(10):
                data = self.packet[0][where+(241+group)*16:where+(242+group)*16]
                vectors = [q14_direction(yaw,group*8+2*i) for i in range(4)]
                bounds = [f(abs(v[axis]) for v in vectors) for axis in (0,1) for f in (min,max)]
                self.assertEqual([int.from_bytes(data[i:i+2],"little") for i in range(0,8,2)],bounds)
                self.assertEqual(data[10:12],bytes((group*8,4)))
                self.assertEqual(data[13:],bytes(3))
        self.assertEqual(self.packet[2]["anchor_packet_workspace_bytes"],96)

    def test_machine_bounds_and_outputs_across_yaws_and_boundary_fractions(self):
        packet,scalar = self.boot(self.packet),self.boot(self.scalar)
        counts = dict(bounds=0,splits=0,max_pending=0)
        def signed32(c,address): return int.from_bytes(read_block(c,address,4),"little",signed=True)
        def bounds(c):
            first,count = c.read8(PK_FIRST),c.read8(PK_COUNT)
            self.assertIn(count,(2,4))
            vectors = [q14_direction(c.read8(br.ANGLE),first+2*i) for i in range(count)]
            nx,ny = c.read16(PK_NX),c.read16(PK_NY)
            lower = nx*min(abs(v[1]) for v in vectors)-ny*max(abs(v[0]) for v in vectors)
            upper = nx*max(abs(v[1]) for v in vectors)-ny*min(abs(v[0]) for v in vectors)
            self.assertEqual((signed32(c,PK_EMIN),signed32(c,PK_EMAX)),(lower,upper))
            pending=c.read8(PK_STACK); self.assertLessEqual(pending,2)
            counts["max_pending"]=max(counts["max_pending"],pending); counts["bounds"]+=1
        def split(c): counts["splits"]+=1
        def rebound(c):
            pending=c.read8(PK_STACK); self.assertLessEqual(pending,2)
            counts["max_pending"]=max(counts["max_pending"],pending)
        packet.breakpoints[self.packet[1]["packet_bounds"]]=bounds
        packet.breakpoints[self.packet[1]["packet_split"]]=split
        packet.breakpoints[self.packet[1]["packet_rebound"]]=rebound
        poses = [(1152,3456,yaw) for yaw in range(0,256,7)]
        poses += [(4*256+fraction,13*256+fraction,yaw) for fraction in (0,1,127,128,255) for yaw in (0,1,63,64,127,128,191,192,255)]
        for px,py,yaw in poses:
            for c in (packet,scalar):
                c.write16(br.PLAYER_XL,px); c.write16(br.PLAYER_YL,py); c.write8(br.ANGLE,yaw)
                c.call_subroutine("cast_all")
                self.assertEqual(c.rom_bank,1); self.assertEqual(c.io[0x70]&7,1)
            for address,count in ((br.RAY_TOPS,80),(br.RAY_STYLES,80),(br.RAY_KEYS,80),(br.RAY_ALONG,80),
                                  (br.RAY_DEPTH,80),(br.RAY_SEGMENT,80),(br.RAY_SURFACE,80),
                                  (br.PIXEL_TOPS,160),(br.PIXEL_STYLES,160),(br.PIXEL_KEYS,160),
                                  (br.PIXEL_ALONG,160),(br.PIXEL_SEGMENT,160),(br.PIXEL_SURFACE,160)):
                self.assertEqual(read_block(packet,address,count),read_block(scalar,address,count),((px,py,yaw),hex(address)))
            self.assertEqual(packet.read8(br.ADAPTIVE_CASTS),scalar.read8(br.ADAPTIVE_CASTS))
        self.assertGreater(counts["bounds"],1000)
        self.assertGreater(counts["splits"],100)
        self.assertEqual(counts["max_pending"],2)


class PacketReuseTests(PacketTests):
    reuse = True


if __name__ == "__main__": unittest.main()
