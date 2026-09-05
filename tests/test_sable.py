"""Native-art, wall-mounting and raster publication acceptance gates."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from lupine3d_v4.artwork import hud_assets
from lupine3d_v4.levels import compile_level
from sm83emu import CGB


class SableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def boot(self):
        c = CGB(self.rom, self.asm.labels)
        c.run(until_pc=self.asm.labels['main_loop'])
        return c

    def test_hud_dictionary_is_disjoint_from_world_and_masked_objects(self):
        c = self.boot(); data, tilemap, _, _ = hud_assets()
        self.assertLessEqual(len(data), 96 * 16)
        self.assertEqual(bytes(c.vram[0][0x200:0x200+len(data)]), data)
        self.assertTrue(all(32 <= tilemap[y*32+x] < 32+len(data)//16
                            for y in range(12,18) for x in range(20)))
        self.assertEqual(br.HUD_PACKET+11, br.MASK_TILES)
        self.assertLessEqual(32*16+len(data), 0x800)

    def test_actual_stat_vector_switches_only_hud_addressing(self):
        c = self.boot()
        self.assertEqual(int.from_bytes(self.rom[0x49:0x4b], 'little'), self.asm.labels['stat_isr'])
        self.assertEqual(c.raster_lcdc, {96: (16,16,0)})
        c.run(until_pc=self.asm.labels['stat_isr'])
        self.assertEqual(c.ly, 96)
        self.assertLess(c.ppu_dots, 80)  # mode 2, before tile fetch
        c.run(until_pc=self.asm.labels['main_loop'])
        expected = c.render_screen().tobytes()
        c.io[0x40] |= 16
        self.assertEqual(c.render_screen().tobytes(), expected)

    def test_hud_packet_freezes_digits_and_literal_exit_state(self):
        c = self.boot(); c.ime = False; c.write8(0xff40,0)
        for health, exit_active, done, label in ((7,0,0,'LOCK'), (65,1,0,'OPEN'), (0,1,0,'DEAD'), (88,1,1,'DONE')):
            c.write8(br.PLAYER_HEALTH,health); c.write8(br.EXIT_ACTIVE,exit_active); c.write8(br.LEVEL_COMPLETE,done)
            c.call_subroutine('prepare_hud_tiles')
            c.write8(br.PLAYER_HEALTH,99)  # publication consumes the prepared snapshot
            c.call_subroutine('update_hud_tiles')
            for page in (0x1800,0x1c00):
                for row in range(2):
                    p = page+(br.HUD_ROW+row)*32+br.HUD_HEALTH_TENS_X
                    self.assertEqual(list(c.vram[0][p:p+2]), [32+2*(health//10)+row,32+2*(health%10)+row])
                p=page+17*32+16
                self.assertEqual(list(c.vram[0][p:p+3]), hud_assets()[3][label])

    def test_fixture_compiler_rejects_unmounted_or_wrong_facing_art(self):
        source = json.loads((br.ROOT/'levels/living_world.json').read_text())
        self.assertEqual(len(compile_level(br.ROOT/'levels/living_world.json').fixtures), 16)
        for fixture in ({'x':4,'y':13,'side':'north','kind':'vent'},
                        {'x':4,'y':11,'side':'west','kind':'access'},
                        {'x':0,'y':0,'side':'north','kind':'light'}):
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'level.json'; altered=copy.deepcopy(source); altered['fixtures']=[fixture]
                path.write_text(json.dumps(altered))
                with self.assertRaises(ValueError): compile_level(path)

    def test_fixture_stencil_requires_both_segment_and_cell(self):
        c=self.boot(); c.ime=False
        c.write8(br.DECAL_RECORD+4,7); c.write8(br.DECAL_RECORD+7,4)
        for i in range(160): c.write8(br.PIXEL_SEGMENT+i,7); c.write8(br.PIXEL_ALONG+i,4)
        c.a=252; c.call_subroutine('fixture_mask'); self.assertEqual(c.a,15)
        c.a=158; c.call_subroutine('fixture_mask'); self.assertEqual(c.a,192)
        for i in range(4,8): c.write8(br.PIXEL_SEGMENT+i,8)
        c.write8(br.PIXEL_ALONG+1,5)
        c.a=0; c.call_subroutine('fixture_mask'); self.assertEqual(c.a,0xb0)

    def test_authored_fixtures_retain_actor_projection_and_use_upper_wall(self):
        c=self.boot(); c.ime=False; c.write8(br.SIM_READY,0); c.write8(br.WORLD_MODE,0)
        c.write16(br.PLAYER_XL,5*256+128); c.write16(br.PLAYER_YL,13*256)
        c.write8(br.ANGLE,192); c.call_subroutine('cast_all'); c.call_subroutine('render_view')
        marker=bytes((17,23,29,2))
        for i,v in enumerate(marker): c.write8(br.SENTINEL_VISIBLE+i,v)
        c.call_subroutine('render_entities')
        self.assertEqual(bytes(c.read8(br.SENTINEL_VISIBLE+i) for i in range(4)),marker)
        count=c.read8(br.SENTINEL_OAM_USED)
        self.assertGreater(count,0); self.assertLessEqual(count,4)
        for i in range(count):
            y=c.read8(br.OAM_SHADOW+(br.ENTITY_OAM_FIRST+i)*4)
            self.assertLessEqual(y,48)  # fixture bottom is above the eye-height horizon
        c.call_subroutine('upload_hidden_page')
        self.assertTrue(c.commit_events[-1]['vblank_safe'])

    def test_every_publication_budget_boundary_finishes_before_line_153(self):
        base=self.boot()
        for dynamic,masked in ((0,0),(0,32),(20,4),(24,0),(24,2),(32,4),(40,0),(96,32)):
            with self.subTest(dynamic=dynamic,masked=masked):
                c=copy.deepcopy(base); c.write8(br.DYN_COUNT,dynamic); c.write8(br.MASK_TILE_COUNT,masked)
                c.call_subroutine('upload_hidden_page')
                self.assertTrue(c.commit_events[-1]['vblank_safe'])
                self.assertGreaterEqual(c.ly,144); self.assertLess(c.ly,153)

    def test_fixture_tiles_cannot_take_reserved_actor_scanline_capacity(self):
        c=self.boot(); c.ime=False; c.call_subroutine('clear_entity_oam_shadow')
        for i in range(144): c.write8(br.WORLD_SCANLINES+i,4)
        c.call_subroutine('render_wall_fixtures')
        self.assertEqual(c.read8(br.SENTINEL_OAM_USED),0)
        self.assertEqual(c.read8(br.MASK_TILE_COUNT),0)


if __name__ == '__main__': unittest.main()
