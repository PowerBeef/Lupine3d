"""Event debt, wrap, scene ownership, coherent OAM and bounded VBlank work."""
import unittest
from test_render_experiments import variant
import build_rom as br
from playtest import read_block,oam_budget
from runtime_observer import RuntimeObserver
from sm83emu import CGB


class ForegroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.build=variant(COMPACT_STRIPS=1,SCANLINE_ADMISSION=1,FOREGROUND_PUBLICATION=1)

    def cpu(self):
        c=CGB(self.build[0],self.build[1]);c.run(until_pc=self.build[1]["main_loop"]);c.ime=False
        return c

    def enqueue(self,c,tick=9):
        old=c.io[0x70]&7;c.write8(0xFF70,2);c.write16(br.SIM_TICK,tick);c.write16(br.SIM_CLOCK,tick+2)
        c.call_subroutine("enqueue_foreground_fire");self.assertEqual(c.io[0x70]&7,2);c.write8(0xFF70,old)

    def consume(self,c):
        old=c.io[0x70]&7;c.write8(0xFF70,4);c.write16(br.FG_TARGET_GENERATION,c.read16(br.WALL_EPOCH))
        c.call_subroutine("consume_foreground_events");c.write8(0xFF70,old)

    def test_full_queue_preserves_pending_and_sequence_wrap(self):
        c=self.cpu();c.write16(br.FG_SEQUENCE,65532)
        for i in range(15):self.enqueue(c,100+i)
        before=bytes(c.wramx[4][0x200:0x2A0]);self.enqueue(c,999)
        self.assertEqual(bytes(c.wramx[4][0x200:0x2A0]),before)
        self.assertEqual(c.read16(br.FG_OVERFLOW),1)
        for count in (4,8,12,15):
            self.consume(c);self.assertEqual(c.read16(br.FG_CONSUMED_SEQUENCE),(65532+count)&65535)
        self.assertEqual(c.read8(br.FG_TAIL),c.read8(br.FG_HEAD))
        self.assertEqual(c.read8(br.FG_ACTIVE),9)
        self.enqueue(c,200);self.consume(c);self.assertEqual(c.read16(br.FG_CONSUMED_SEQUENCE),12)

    def test_producer_payload_is_complete_before_head_is_visible(self):
        c=self.cpu();seen=[]
        def commit(cpu):
            head=cpu.read8(br.FG_HEAD);record=bytes(cpu.wramx[4][0x200+head*10:0x20A+head*10])
            seen.append(record);self.assertEqual(cpu.read8(br.FG_TAIL),head)
        c.breakpoints[c.symbols["foreground_producer_commit"]]=commit
        self.enqueue(c,65534)
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][2:6],bytes((254,255,0,0)))
        self.assertEqual(seen[0][8],1)

    def test_future_scene_waits_and_reload_clears_event_ownership(self):
        c=self.cpu();self.enqueue(c);current=c.read16(br.WALL_EPOCH)
        c.write8(0xFF70,4);c.write16(br.FG_TARGET_GENERATION,(current-1)&65535)
        c.call_subroutine("consume_foreground_events");self.assertEqual(c.read8(br.FG_TAIL),0)
        c.write8(0xFF70,2);c.call_subroutine("load_level")
        self.assertEqual(c.read8(br.FG_HEAD),0);self.assertEqual(c.read8(br.FG_TAIL),0)
        self.assertEqual(c.read8(br.FG_ACTIVE),0);self.assertEqual(c.read8(br.FG_READY),0)
        self.assertNotEqual(c.read16(br.WALL_EPOCH),current)

    def test_foreground_dma_preserves_world_and_mask_ownership(self):
        c=self.cpu();self.enqueue(c)
        old_oam=bytes(c.oam);old_vram=[bytes(v) for v in c.vram];old_page=c.read8(br.OBJ_PAGE);old_present=c.presentations
        c.ly=144;c.ppu_dots=0;c.write8(0xFF70,3);before=c.cycles
        c.call_subroutine("foreground_vblank")
        expected=bytearray(old_oam);expected[36]=72
        self.assertEqual(bytes(c.oam),bytes(expected));self.assertEqual([bytes(v) for v in c.vram],old_vram)
        self.assertEqual(c.read8(br.OBJ_PAGE),old_page);self.assertEqual(c.presentations,old_present)
        self.assertEqual(c.io[0x70]&7,3);self.assertEqual(c.read8(br.OAM_DMA_HRAM+1),0xC8)
        self.assertLess(c.cycles-before,9*912);self.assertLess(c.ly,153)
        self.assertLessEqual(oam_budget(c)["max_oam_per_scanline"],10)
        # A staged world packet owns the next VBlank; this lane must abstain.
        self.enqueue(c,20);c.write8(br.FG_WORLD_PENDING,1);serial=c.read8(br.FG_SERIAL);head=c.read8(br.FG_HEAD);tail=c.read8(br.FG_TAIL)
        c.call_subroutine("foreground_vblank")
        self.assertEqual((c.read8(br.FG_SERIAL),c.read8(br.FG_HEAD),c.read8(br.FG_TAIL)),(serial,head,tail))

    def test_worst_queue_work_and_register_preservation(self):
        c=self.cpu()
        for i in range(15):self.enqueue(c,i)
        c.ly=144;c.ppu_dots=0;c.io[0x0F]=0;c.ie=0
        c.af=0x12B0;c.bc=0x2345;c.de=0x6789;c.hl=0xABCD;c.write8(0xFF70,3)
        registers=(c.af,c.bc,c.de,c.hl);before=c.cycles
        c.call_subroutine("vblank_isr")
        self.assertEqual((c.af,c.bc,c.de,c.hl),registers);self.assertEqual(c.io[0x70]&7,3)
        self.assertLess(c.cycles-before,8*912);self.assertLess(c.ly,153)
        self.assertEqual(c.read8(br.FG_TAIL),2)

    def test_full_commit_does_not_replay_consumed_flash(self):
        c=self.cpu();self.enqueue(c);self.consume(c)
        c.write8(br.FG_ACTIVE,0);c.write8(br.FLASH,9)  # older immutable snapshot still carries the legacy event
        c.call_subroutine("prepare_foreground_commit")
        self.assertEqual(c.read8(br.OAM_SHADOW+36),0)
        self.assertEqual(c.read16(br.FG_CONSUMED_SEQUENCE),1)
        c.call_subroutine("finish_foreground_commit")
        self.assertEqual(c.wramx[4][0x100+36],0);self.assertEqual(c.read8(br.FG_WORLD_PENDING),0)

    def test_maximal_staged_world_packet_and_late_interrupt(self):
        c=self.cpu();self.enqueue(c)
        # A late VBlank entry cannot borrow the normal entry's timing budget.
        c.ly=145;c.ppu_dots=0;tail=c.read8(br.FG_TAIL);serial=c.read8(br.FG_SERIAL)
        c.call_subroutine("foreground_vblank")
        self.assertEqual((c.read8(br.FG_TAIL),c.read8(br.FG_SERIAL)),(tail,serial))
        c.write8(0xFF70,1);c.write8(br.DYN_COUNT,96);c.write8(br.MASK_TILE_COUNT,32)
        old=bytes(c.oam);stages=[]
        def before_final(cpu):
            stages.append(cpu.frame_count)
            self.assertEqual(bytes(cpu.oam),old)
            self.assertEqual(cpu.read8(br.FG_WORLD_PENDING),1)
        c.breakpoints[c.symbols["upload_packet_ready"]]=before_final
        c.ime=True;c.call_subroutine("upload_hidden_page")
        event=c.commit_events[-1]
        self.assertEqual(event['blocks'],176);self.assertTrue(event['staged']);self.assertTrue(event['vblank_safe'])
        self.assertTrue(stages);self.assertEqual(c.read8(br.FG_WORLD_PENDING),0)
        self.assertEqual(bytes(c.wramx[4][0x100:0x1A0]),bytes(c.oam))
        self.assertEqual(c.read16(br.FG_CONSUMED_SEQUENCE),1)
        self.assertEqual(c.oam[36],72)


if __name__=="__main__":unittest.main()
