"""Byte-complete packed ROM decoding and emitted lookup boundaries."""
import hashlib
import unittest
from test_render_experiments import variant
import build_rom as br
from lupine3d_v4.projection_storage import read_packed,pack_projection
from sm83emu import CGB


class ProjectionStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builds={mode:variant(COMPACT_STRIPS=1,PROJECTION_STORAGE=mode) for mode in ("direct","paged256","hybrid256")}
        cls.logical=br.make_projection_top_lut()

    def test_all_logical_bytes_and_deterministic_packing(self):
        for mode,(rom,labels,manifest) in self.builds.items():
            actual=bytes(read_packed(rom,i,mode) for i in range(len(self.logical)))
            self.assertEqual(actual,self.logical,mode)
            packed,fmt=pack_projection(mode)
            self.assertEqual(packed,rom[0x8000:0x8000+len(packed)])
            self.assertEqual(fmt,manifest["projection_storage_format"])
            for bank in range(br.PRODUCT_LUT_BASE_BANK,br.RAY_SETUP_ROM_BANK):
                self.assertEqual(rom[bank*0x4000:(bank+1)*0x4000],self.builds["direct"][0][bank*0x4000:(bank+1)*0x4000])
            if mode!="direct":
                self.assertLess(len(packed),len(self.logical))
                for page in range(len(self.logical)//256):
                    offset=(page//4096)*0x4000+(page%4096)*3
                    self.assertLessEqual(offset%0x4000,0x3FFD)
                    self.assertEqual(packed[offset+1],0)

    def test_emitted_lookup_every_page_and_payload_edges(self):
        for mode in ("paged256","hybrid256"):
            rom,labels,_=self.builds[mode];c=CGB(rom,labels);c.write8(0xFF70,1)
            for page in range(len(self.logical)//256):
                for offset in (0,126,254):
                    logical=page*256+offset;slice_index=logical//1024;distance=(logical%1024)//2
                    c.hl=slice_index;c.write8(br.D32_LOW,distance&255);c.write8(br.D32_HIGH,distance>>8)
                    c.call_subroutine("project_paged_read")
                    self.assertEqual(bytes((c.read8(br.TOP_RESULT),c.read8(br.DEPTH_RESULT))),self.logical[logical:logical+2],(mode,page,offset))
                    self.assertEqual(c.rom_bank,1)

    def test_prepared_metadata_and_raw_projection(self):
        for mode in ("paged256","hybrid256"):
            rom,labels,_=self.builds[mode];direct=self.builds["direct"][0]
            for yaw in range(256):
                for record in range(241):
                    base=br.RAY_SETUP_ROM_BANK*0x4000+yaw*4096+record*16
                    for offset in (7,9):
                        bank,high=direct[base+offset:base+offset+2]
                        logical=(bank-br.PROJECTION_LUT_BASE_BANK)*16+(high-0x40)//4
                        self.assertEqual(int.from_bytes(rom[base+offset:base+offset+2],"little"),logical)
                    self.assertEqual(rom[base:base+7],direct[base:base+7]);self.assertEqual(rom[base+11:base+16],direct[base+11:base+16])
            c=CGB(rom,labels);c.write8(0xFF70,1)
            for component in range(128):
                for correction in range(110,128):
                    distance=(component*73+correction*13)%512
                    c.write8(br.DDA_DIST_L,(distance*8)&255);c.write8(br.DDA_DIST_H,(distance*8)>>8)
                    c.write8(br.DDA_AXIS,0);c.write8(br.DDA_ABS_X,component);c.write8(br.DDA_CORRECTION,correction);c.write8(br.Q14_RECORD,255)
                    c.call_subroutine("project_hit")
                    index=(component*18+correction-110)*1024+distance*2
                    self.assertEqual(bytes((c.read8(br.TOP_RESULT),c.read8(br.DEPTH_RESULT))),self.logical[index:index+2])
                    self.assertEqual(c.rom_bank,1)


if __name__=="__main__":unittest.main()
