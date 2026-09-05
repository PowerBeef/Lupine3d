"""Prepared ROM records versus camera math and actual SM83 bank addressing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from sm83emu import CGB
from lupine3d_v4.precision import q14_direction


class RaySetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    def test_all_61696_records_preserve_vectors_corrections_and_projection_addresses(self):
        tables = br.make_tables()
        first = br.RAY_SETUP_ROM_BANK * 16384
        for angle in range(256):
            for record in range(241):
                if record == 240:
                    offset, correction = 0, 127
                else:
                    i, prefix = (record, "ray") if record < 80 else (record-80, "physical")
                    offset = int.from_bytes(tables[prefix+"_offsets"][i*2:i*2+2],"little",signed=True)
                    correction = tables[prefix+"_corrections"][i]
                direction = (4*angle+offset) % 1024
                values = [tables[key][direction] for key in ("ray_dx","ray_dy")]
                values = [x-256 if x>=128 else x for x in values]
                expected = [abs(x) for x in values]+[1 if x>0 else 255 if x<0 else 0 for x in values]
                where = first+(angle*256+record)*16
                data = self.rom[where:where+16]
                self.assertEqual(list(data[:4]),expected)
                self.assertEqual(int.from_bytes(data[4:6],"little"),direction)
                self.assertEqual(data[6],correction)
                for axis in (0,1):
                    slice_index = abs(values[axis])*18+correction-110
                    bank, high = data[7+axis*2:9+axis*2]
                    self.assertEqual(bank*16384+high*256-0x4000,
                                     br.PROJECTION_LUT_BASE_BANK*16384+slice_index*1024)
                    for distance in (0,255,256,511):
                        address = high*256+distance*2
                        self.assertTrue(0x4000<=address<0x7FFF)
                self.assertEqual([int.from_bytes(data[i:i+2],"little") for i in (11,13)],
                                 [abs(x) for x in q14_direction(angle,record)])
                self.assertEqual(data[15],0)
        self.assertEqual(len(self.rom),4*1024*1024)
        self.assertEqual(self.manifest["prepared_ray_wram_bytes"],8 if br.CAMERA_SETUP else 4)
        self.assertLessEqual(first+br.RAY_SETUP_ROM_BYTES,len(self.rom))

    def test_sm83_record_load_crosses_all_camera_banks_and_restores_bank_one(self):
        c = CGB(self.rom,self.asm.labels); c.run(until_pc=self.asm.labels["main_loop"])
        c.ime = False; c.write8(br.SIM_READY,0)
        addresses = (br.DDA_ABS_X,br.DDA_ABS_Y,br.DDA_STEP_X,br.DDA_STEP_Y,
                     br.DDA_ANGLE_L,br.DDA_ANGLE_H,br.DDA_CORRECTION,
                     br.RAY_PROJECTION_X,br.RAY_PROJECTION_X+1,br.RAY_PROJECTION_Y,br.RAY_PROJECTION_Y+1,
                     br.Q14_X,br.Q14_X+1,br.Q14_Y,br.Q14_Y+1)
        for angle in range(256):
            for record in (0,15,16,79,80,159,239,240):
                c.write8(br.ANGLE,angle); c.write8(br.Q14_RECORD,record)
                c.call_subroutine("load_ray_setup")
                where = br.RAY_SETUP_ROM_BANK*16384+(angle*256+record)*16
                self.assertEqual(bytes(c.read8(addr) for addr in addresses),self.rom[where:where+15])
                self.assertEqual(c.rom_bank,1)
