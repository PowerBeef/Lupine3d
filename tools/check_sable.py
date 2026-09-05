#!/usr/bin/env python3
"""Emitted-ROM checks for the opt-in compact display / Sable art candidate."""
import hashlib
import json
from pathlib import Path
import build_rom as b
from sm83emu import CGB
from playtest import validate_frame,apply_diagnostic_camera,oam_budget
from lupine3d_v4.sprite_assets import evidence,compile_sheet,compile_frame,frames

def check(output):
    assert b.COMPACT_DISPLAY and b.SABLE_ART
    rom,a,meta=b.make_rom(); checks={}; captures=[]
    def boot():
        c=CGB(rom,a.labels);c.run(until_pc=a.labels['main_loop']);return c
    c=boot();assert c.raster_lcdc=={b.VIEW_HEIGHT:(16,16,0)}
    assert b.VIEW_MAP_BYTES==b.VIEW_HEIGHT*4
    assert b.STRIP_SCRATCH==(0xC8E0 if b.SLIM_DISPLAY else 0xC7C0)
    assert bytes(c.vram[1][0x200:0x700])==compile_sheet('shotgun',paired=True)
    assert bytes(c.vram[1][0x700:0x760])==compile_sheet('reticle')+compile_sheet('flash')
    assert len(b.make_entity_tiles())==242*16 and len(b.hud_assets()[0])<=96*16
    checks['cold_art_and_raster_boundary']=True
    # Every translated atlas signature independently composes to its unchanged
    # checked-in payload; all new/near-clipped signatures remain exact misses.
    for offset in range(0,len(b.TILE_ATLAS_ENTRIES),11):
        row=b.TILE_ATLAS_ENTRIES[offset:offset+11];y,dark=row[:2]
        _,tile=b.reference_tile_signature_and_bytes(list(row[2:10]),[(dark>>(7-x))&1 for x in range(8)],y)
        assert tile==b.TILE_ATLAS_TILES[(row[10]-b.ATLAS_TILE_BASE)*16:(row[10]-b.ATLAS_TILE_BASE+1)*16]
    checks['every_translated_atlas_pattern']=True
    if b.SLIM_DISPLAY:
        # Independent pixel coverage for the self-mirrored centre tile: these
        # far walls have both boundaries inside the same eight-pixel strip.
        for top in (57,58):
            _,tile=b.reference_tile_signature_and_bytes([top]*8,[0]*8,56)
            for row in range(8):
                y=56+row
                expected=0 if y<top else 1 if y>=120-top else 3 if y in (top,119-top) else 2
                actual=((tile[2*row]>>7)&1)|(((tile[2*row+1]>>7)&1)<<1)
                assert actual==expected,(top,row,actual,expected)
        c=boot();c.ime=False;c.write8(0xff40,0);c.write8(b.SIM_READY,0)
        for pattern in ((57,)*8,(58,)*8,(0,56,57,58,58,57,56,0)):
            tops=list(pattern)+[56]*152;styles=[0,1]*4+[0]*152
            for x in range(160):
                c.write8(b.PIXEL_TOPS+x,tops[x]);c.write8(b.PIXEL_STYLES+x,styles[x])
            c.call_subroutine('render_view')
            dynamic,tilemap,count,overflow=b.reference_compose_view(tops,styles)
            assert not overflow and c.read8(b.DYN_COUNT)==count,(pattern,overflow,c.read8(b.DYN_COUNT),count)
            assert bytes(c.read8(b.VIEW_MAP+i) for i in range(b.VIEW_MAP_BYTES))==tilemap
            assert bytes(c.read8(b.DYNAMIC_TILES+i) for i in range(len(dynamic)))==dynamic
        checks['centre_tile_two_boundary_coverage']=True
    c=boot();c.ime=False;c.write8(0xff40,0)
    for y in range(0,b.FOLDED_ROWS*8 if b.COMPACT_STRIPS else b.VIEW_HEIGHT,8):
        c.write8(b.TILE_Y0,y)
        for top in range(b.HORIZON-1):
            c.a=top;c.call_subroutine('compute_strip_state')
            logical=b.reference_strip_state(top,y)
            expected=b.STORED_STRIP_STATES.index(logical)
            assert c.a==expected,(top,y,c.a,expected)
    checks['complete_legal_strip_selector_domain']=True
    # Boundaries on both sides of stage thresholds, including maximal packet.
    windows=[]
    for dyn,mask in ((0,0),(8,0),(9,0),(0,16),(0,18),(0,32),(8,16),(9,16),(24,0),(25,0),(48,0),(49,0),(16,32),(17,32),(71,0),(72,0),(73,0),(40,32),(41,32),(96,0),(96,16),(96,32)):
        c=boot();c.write8(b.SIM_READY,0);c.write8(b.DYN_COUNT,dyn);c.write8(b.MASK_TILE_COUNT,mask)
        old_page=c.read8(b.CURRENT_PAGE);old_oam=bytes(c.oam)
        violations=[];original=c.write8
        def observed(address,value):
            if 0x8000<=address<0xA000 and c.io[0x40]&128:
                if c.ly<144 or c.ly>=153:violations.append((address,c.ly,c.ppu_dots))
                if 0x9800<=address<0xA000:
                    page=int(address>=0x9C00)
                    if page==old_page and address%0x400<b.VIEW_MAP_BYTES:raise AssertionError('visible world map CPU write')
            original(address,value)
        c.write8=observed
        c.pc=a.labels['upload_hidden_page'];c.run(until_pc=a.labels['upload_packet_ready'])
        assert bytes(c.oam)==old_oam and c.read8(b.CURRENT_PAGE)==old_page
        c.run(until_presentations=1);event=c.commit_events[-1]
        assert event['blocks']==dyn+mask+48 and event['vblank_safe'],event
        assert not violations,violations[:5]
        page=c.read8(b.CURRENT_PAGE);offset=0x1800+page*0x400
        assert bytes(c.vram[0][offset:offset+b.VIEW_MAP_BYTES])==bytes(c.read8(b.VIEW_MAP+i) for i in range(b.VIEW_MAP_BYTES))
        assert bytes(c.vram[1][offset:offset+b.VIEW_MAP_BYTES])==bytes(c.read8(b.VIEW_ATTRIBUTES+i) for i in range(b.VIEW_MAP_BYTES))
        windows.append({'dynamic':dyn,'mask':mask,'blocks':event['blocks'],'commit_ly':event['ly'],'staged':event['staged']})
    checks['publication_cpu_and_dma_windows']=True
    output.mkdir(parents=True,exist_ok=True)
    for index,pose in enumerate(((1152,3456,192),(1408,3328,192),(1152,3136,192),(1152,3100,191),(1152,3100,255),(1408,3200,0))):
        c=boot();c.write8(b.SIM_READY,0);apply_diagnostic_camera(c,{'pose':pose});c.run(until_presentations=2)
        validate_frame(c);im=c.render_screen();path=output/f'pose-{index}.png';im.save(path);im.resize((640,576),resample=0).save(output/f'pose-{index}-4x.png')
        captures.append({'file':path.name,'pose':pose,'pixels_sha256':hashlib.sha256(im.tobytes()).hexdigest()})
    checks['geometry_and_all_published_rows']=True
    from quality_witnesses import scene_corpus,setup,plane_hit
    near=next(scene for scene in scene_corpus() if scene.name=='close_clipped_wall')
    c=boot();setup(c,near);c.run(until_presentations=1)
    # Independent rational face enumeration puts the plane well inside the
    # enlarged vertical clipping interval. Every affected column fills it.
    for x in range(160):
        depth=plane_hit(near,x)['depth_q8']
        assert depth < 7680/b.HORIZON
        assert c.read8(b.PIXEL_TOPS+x)==0
    checks['independent_near_plane_clipping']=True
    c=boot();c.ime=False;c.write8(0xff40,0);c.write8(b.SIM_READY,0)
    # Force all twelve source frames through all three emitted LOD paths and
    # verify actual masked WRAM bytes rather than merely host frame indexing.
    for lod,name,base in ((0,'sentinel_near',b.SENTINEL_NEAR_TILE_BASE),(1,'sentinel_mid',b.SENTINEL_MID_TILE_BASE),(2,'sentinel_far',b.SENTINEL_FAR_TILE_BASE)):
        for frame in range(12):
            c.call_subroutine('clear_entity_oam_shadow');c.write8(b.SENTINEL_LOD,lod);c.write8(b.SENTINEL_ANIM,frame)
            c.write8(b.ENTITY_FOOT_Y,88);c.write8(b.SENTINEL_SCREEN_X,72);c.write8(b.ENTITY_SCREEN_LEFT,255);c.write8(b.ENTITY_SCREEN_RIGHT,255)
            c.call_subroutine('render_actor_atomic')
            expected=compile_frame(name,frame,column_major=True)
            assert bytes(c.read8(b.MASK_TILES+i) for i in range(len(expected)))==expected,(name,frame)
    checks['all_36_emitted_enemy_cels']=True
    for age,cel in ((0,1),(4,2),(10,3),(16,4),(24,0)):
        c.write16(b.SHOT_TICK,65530);c.write16(b.FRAME_TICK,(65530+age)&65535);c.write8(b.SHOT_ACTIVE,1);c.write8(b.FLASH,0)
        c.call_subroutine('animate_weapon');assert c.read8(b.OAM_SHADOW+2)==32+16*cel
    c.write8(b.FLASH,9);c.write8(b.SHOT_ACTIVE,0);c.call_subroutine('animate_weapon');assert c.read8(b.OAM_SHADOW+2)==48
    for tick in (65534,1,2):
        c.write16(b.SIM_TICK,tick);c.call_subroutine('stamp_shot');assert c.read16(b.SHOT_TICK)==tick
    checks['weapon_phases_rapid_restarts_wrap_pending_flash']=True
    for kind,ages,expected in ((1,(0,4,7),(6,7,7)),(2,(0,4,7),(8,8,8)),(3,(0,12,24),(9,10,11))):
        c.write8(b.ACTOR_REACTION,kind);c.write16(b.ACTOR_REACTION_TICK,65530)
        for age,cel in zip(ages,expected):
            c.write16(b.FRAME_TICK,(65530+age)&65535);c.call_subroutine('select_actor_animation');assert c.read8(b.SENTINEL_ANIM)==cel
    c.write16(b.SIM_TICK,30);c.call_subroutine('expire_actor_reaction');assert c.read8(b.ACTOR_REACTION)==0
    checks['reaction_and_death_clock_wrap']=True
    for health,hurt,tick,portrait in ((99,0,8,0),(99,0,62 if b.SLIM_DISPLAY else 0,1),(65,1,8,2),(0,0,8,3)):
        c.write8(b.PLAYER_HEALTH,health);c.write8(b.HURT_ACTIVE,hurt);c.write16(b.FRAME_TICK,tick)
        c.write8(b.HUD_PACKET+b.HUD_PACKET_BYTES,0xA5);c.call_subroutine('prepare_hud_tiles')
        packet=bytes(c.read8(b.HUD_PACKET+i) for i in range(b.HUD_PACKET_BYTES))
        assert packet[b.HUD_PORTRAIT_OFFSET:b.HUD_PORTRAIT_OFFSET+b.HUD_PORTRAIT_TILES]==bytes(b.hud_assets()[3]['portrait'+str(portrait)])
        c.write8(b.PLAYER_HEALTH,1);c.write16(b.FRAME_TICK,77);c.call_subroutine('update_hud_tiles')
        for page in (0x1800,0x1C00):
            assert bytes(c.vram[0][page+b.HUD_HEALTH_ROW*32+3:page+b.HUD_HEALTH_ROW*32+5])==packet[:2]
            for i in range(b.HUD_PORTRAIT_TILES):
                assert c.vram[0][page+(b.HUD_PORTRAIT_ROW+i//2)*32+9+i%2]==packet[b.HUD_PORTRAIT_OFFSET+i]
            assert bytes(c.vram[0][page+b.HUD_CAPTION_ROW*32+b.HUD_CAPTION_X:page+b.HUD_CAPTION_ROW*32+b.HUD_CAPTION_X+2])==packet[b.HUD_STATUS_OFFSET:b.HUD_STATUS_OFFSET+2]
        assert c.read8(b.HUD_PACKET+b.HUD_PACKET_BYTES)==0xA5
    checks['hud_portraits_snapshot_packet_and_bounds']=True
    # Static icon and EXIT label stay outside every dynamic tile destination.
    c=boot();c.ime=False;c.write8(0xff40,0)
    static_slots=tuple((b.VIEW_ROWS+row)*32+13 for row in range(b.HUD_HEIGHT//8))
    expected=tuple(c.vram[0][0x1800+i] for i in static_slots)
    for count in range(5):
        c.write8(b.ACTOR_COUNT,count)
        for i in range(4):c.write8(b.ENTITY_SLOTS+i*16+4,b.SENTINEL_DORMANT)
        c.call_subroutine('prepare_hud_tiles');c.call_subroutine('update_hud_tiles')
        if b.SLIM_DISPLAY:
            assert c.read8(b.HUD_PACKET+4)==b.HUD_SMALL_DIGIT_BASE+count
        else:
            assert c.read8(b.HUD_PACKET+4)==b.HUD_SMALL_DIGIT_BASE
            assert c.read8(b.HUD_PACKET+5)==b.HUD_SMALL_DIGIT_BASE+count
        for page in (0x1800,0x1C00):
            assert tuple(c.vram[0][page+i] for i in static_slots)==expected
    assert b.HUD_PACKET_BYTES==(16 if b.SLIM_DISPLAY else 15)
    # Exercise the live-to-cleared objective transition and terminal priority.
    # Verify the immutable packet and both published map copies, not only
    # the caption: the main status must change coherently with it.
    for health,done,exit_active,status in ((99,0,0,'LOCK'),(99,0,1,'OPEN'),
                                           (0,0,1,'DEAD'),(99,1,1,'DONE')):
        c.write8(b.PLAYER_HEALTH,health);c.write8(b.LEVEL_COMPLETE,done);c.write8(b.EXIT_ACTIVE,exit_active)
        c.call_subroutine('prepare_hud_tiles')
        expected=bytes(b.hud_assets()[3]['caption_'+status]+b.hud_assets()[3][status])
        assert bytes(c.read8(b.HUD_PACKET+b.HUD_STATUS_OFFSET+i) for i in range(5))==expected
        c.write8(b.EXIT_ACTIVE,1-exit_active)
        c.call_subroutine('update_hud_tiles')
        for page in (0x1800,0x1C00):
            caption=bytes(c.vram[0][page+b.HUD_CAPTION_ROW*32+b.HUD_CAPTION_X+i] for i in range(2))
            status_tiles=bytes(c.vram[0][page+b.HUD_STATUS_ROW*32+16+i] for i in range(3))
            assert caption+status_tiles==expected,(status,page)
            if b.SLIM_DISPLAY:
                lower=bytes(c.vram[0][page+(b.HUD_STATUS_ROW+1)*32+16+i] for i in range(3))
                assert lower==bytes(tile+1 for tile in expected[2:]),(status,page)
    checks['objective_transition_and_terminal_publication']=True
    if b.SLIM_DISPLAY:
        # Read published VRAM, including both pages and every digit, portrait
        # and terminal caption. Dynamic tiles must retain the static divider.
        for health,hurt,tick,done in ((n*11,0,8,0) for n in range(10)):
            c.write8(b.PLAYER_HEALTH,health);c.write8(b.HURT_ACTIVE,hurt)
            c.write16(b.FRAME_TICK,tick);c.write8(b.LEVEL_COMPLETE,done)
            c.call_subroutine('prepare_hud_tiles');c.call_subroutine('update_hud_tiles')
            for page in (0x1800,0x1C00):
                for column in range(20):
                    tile=c.vram[0][page+b.VIEW_ROWS*32+column]
                    assert bytes(c.vram[0][tile*16:tile*16+2])==b'\xff\x00',(health,page,column)
        for hurt,tick,done in ((0,0,0),(1,8,0),(0,8,1)):
            c.write8(b.PLAYER_HEALTH,99);c.write8(b.HURT_ACTIVE,hurt)
            c.write16(b.FRAME_TICK,tick);c.write8(b.LEVEL_COMPLETE,done)
            c.call_subroutine('prepare_hud_tiles');c.call_subroutine('update_hud_tiles')
            for page in (0x1800,0x1C00):
                for column in range(20):
                    tile=c.vram[0][page+b.VIEW_ROWS*32+column]
                    assert bytes(c.vram[0][tile*16:tile*16+2])==b'\xff\x00',(hurt,tick,done,page,column)
        checks['continuous_divider_all_dynamic_states_and_both_maps']=True
        def hud_pixel(page,x,y):
            tile=c.vram[0][page+(b.VIEW_ROWS+y//8)*32+x//8]
            address=tile*16+(y%8)*2;bit=7-x%8
            return ((c.vram[0][address]>>bit)&1)|(((c.vram[0][address+1]>>bit)&1)<<1)
        # Full chassis rails, not only the divider, survive every replacement.
        # The four corner highlights and three vent notches are intentional.
        for health,hurt,tick,done in ([(n*11,0,8,0) for n in range(10)]+
                                     [(99,0,62,0),(99,1,8,0),(99,0,8,1)]):
            c.write8(b.PLAYER_HEALTH,health);c.write8(b.HURT_ACTIVE,hurt)
            c.write16(b.FRAME_TICK,tick);c.write8(b.LEVEL_COMPLETE,done)
            c.call_subroutine('prepare_hud_tiles');c.call_subroutine('update_hud_tiles')
            for page in (0x1800,0x1C00):
                for y in (0,1,2,21,22):
                    for x in range(160):
                        expected=1 if y<2 or 3<=x<157 else 0
                        if y==1 and x in (4,5,154,155):expected=2
                        if y==21 and x in (8,12,16):expected=0
                        assert hud_pixel(page,x,y)==expected,(health,hurt,tick,done,x,y)
                assert hud_pixel(page,80,6)==2, 'helmet highlight lost during expression'
                assert all(hud_pixel(page,x,3)==0 for x in range(128,152)), 'objective touches upper bevel'
                assert all(hud_pixel(page,x,9)==0 for x in range(128,152)), 'objective lines lack separation'
        checks['steel_chassis_and_portrait_highlights_all_states']=True
    checks['hud_icon_exit_and_all_actor_counts']=True
    for used in range(13,17):
        c.call_subroutine('clear_entity_oam_shadow');c.write8(b.SENTINEL_OAM_USED,used);c.write8(b.MASK_TILE_COUNT,used*2)
        c.write8(b.SENTINEL_LOD,0);c.write8(b.SENTINEL_ANIM,11)
        c.write8(b.ENTITY_FOOT_Y,88);c.write8(b.SENTINEL_SCREEN_X,72);c.write8(b.ENTITY_SCREEN_LEFT,255);c.write8(b.ENTITY_SCREEN_RIGHT,255)
        c.call_subroutine('render_actor_atomic')
        delta=c.read8(b.SENTINEL_OAM_USED)-used;assert delta in (0,1,2,4) and delta<=16-used
        assert c.read8(b.MASK_TILE_COUNT)==2*(used+delta)
    checks['atomic_capacity_fallback_no_partial_actor']=True
    c.call_subroutine('init_art_clocks');c.write8(b.SHOT_ACTIVE,1);c.call_subroutine('world_to_buffer');c.write8(0xff70,2);c.call_subroutine('buffer_to_world')
    assert c.read8(b.SHOT_ACTIVE)==1
    c.call_subroutine('init_art_clocks');assert c.read8(b.SHOT_ACTIVE)==0 and c.read8(b.HINT_ACTIVE)==1
    checks['snapshot_and_reload_clock_ownership']=True
    for terminal in (b.PLAYER_HEALTH,b.LEVEL_COMPLETE):
        c.write8(b.PLAYER_HEALTH,0 if terminal==b.PLAYER_HEALTH else 99)
        c.write8(b.LEVEL_COMPLETE,1 if terminal==b.LEVEL_COMPLETE else 0);c.write8(b.PRESSED,0)
        c.write8(b.SHOT_ACTIVE,1);c.write8(b.FLASH,9);c.write8(b.ACTOR_REACTION,3)
        for i in range(4):c.write8(b.ENTITY_SLOTS+i*16+14,3)
        c.write16(b.SIM_TICK,65535);c.call_subroutine('simulation_tick')
        c.write16(b.SIM_TICK,0);c.call_subroutine('simulation_tick')
        assert c.read8(b.SHOT_ACTIVE)==0 and c.read8(b.ACTOR_REACTION)==0
        assert all(c.read8(b.ENTITY_SLOTS+i*16+14)==0 for i in range(4))
        assert c.read8(b.FLASH)==9
    checks['terminal_state_wrap_cannot_replay_cosmetics']=True
    result={'schema':'sable.qualification.v1','rom_sha256':hashlib.sha256(rom).hexdigest(),'configuration':b.RENDER_CONFIG,'checks':checks,'assets':evidence(),'publication_windows':windows,'captures':captures,'physical_hardware_tested':False,'passed':all(checks.values())}
    (output/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=b.BUILD/'sable-v2/checks');args=p.parse_args();check(args.output_dir)
