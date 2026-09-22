#!/usr/bin/env python3
"""Emitted-ROM checks for the opt-in compact display / Sable art candidate."""
import hashlib
import json
from pathlib import Path
import build_rom as b
from sm83emu import CGB, run_to_world
from playtest import validate_frame,apply_diagnostic_camera,oam_budget
from lupine3d_v4.sprite_assets import evidence,compile_sheet,compile_frame,frames

FIXTURES=Path(__file__).resolve().parents[1]/'playtests'/'fixtures'

def hud_fixture():
    """The HUD art contract for this profile: selection tables and pinned pixels.

    Slim carries the full steel-HUD fixture (chassis rows, points, spans and
    the divider); the compact profile keeps only the selection tables, since
    its HUD art was never pinned pixel by pixel.
    """
    if b.SLIM_DISPLAY:
        fixture=json.loads((FIXTURES/'steel_hud_v10.json').read_text())
        assert fixture['schema']=='lupine3d.hud-fixture.v1',fixture['schema']
        return fixture
    return {'portraits':{'cases':[[99,0,8,0],[99,0,0,1],[65,1,8,2],[0,0,8,3]]},
            'status':{'cases':[[99,0,0,'LOCK'],[99,0,1,'OPEN'],[0,0,1,'DEAD'],[99,1,1,'DONE']]}}

def check(output,snapshot_mode='check'):
    assert b.COMPACT_DISPLAY and b.SABLE_ART
    rom,a,meta=b.make_rom(); checks={}; captures=[]
    from snapshot import Suite
    snapshots=None if snapshot_mode is None else Suite('sable',mode=snapshot_mode,rom_sha256=hashlib.sha256(rom).hexdigest(),configuration_id=meta['configuration_id'])
    def boot():
        c=CGB(rom,a.labels);run_to_world(c);return c
    c=boot();assert c.raster_lcdc=={b.VIEW_HEIGHT:(16,16,0)}
    assert b.VIEW_MAP_BYTES==b.VIEW_HEIGHT*4
    assert b.STRIP_SCRATCH==(0xC8E0 if b.SLIM_DISPLAY else 0xC7C0)
    assert bytes(c.vram[1][0x200:0x700])==compile_sheet('shotgun',paired=True)
    assert bytes(c.vram[1][0x700:0x760])==compile_sheet('reticle')+compile_sheet('flash')
    assert len(b.make_entity_tiles())==242*16 and len(b.hud_assets()[0])<=96*16
    checks['cold_art_and_raster_boundary']=True
    if b.TEXTURED_WALLS:
        # The kernel's window blocks and their directory are the reference's
        # tables, bank for bank; the flat atlas is retired under this profile.
        from lupine3d_v4 import texture_assets as ta
        for bank,offset,payload in ta.window_payloads(b.TEXTURE_WINDOW_ROM_BANK_BASE):
            assert rom[bank*0x4000+offset:bank*0x4000+offset+len(payload)]==payload,(bank,offset)
        directory=a.labels['tex_block_directory'];entry=ta.block_directory(b.TEXTURE_WINDOW_ROM_BANK_BASE)
        assert rom[directory:directory+len(entry)]==entry
        checks['texture_window_blocks_and_directory']=True
    else:
        # Every translated atlas signature independently composes to its unchanged
        # checked-in payload; all new/near-clipped signatures remain exact misses.
        for offset in range(0,len(b.TILE_ATLAS_ENTRIES),11):
            row=b.TILE_ATLAS_ENTRIES[offset:offset+11];y,dark=row[:2]
            _,tile=b.reference_tile_signature_and_bytes(list(row[2:10]),[(dark>>(7-x))&1 for x in range(8)],y)
            assert tile==b.TILE_ATLAS_TILES[(row[10]-b.ATLAS_TILE_BASE)*16:(row[10]-b.ATLAS_TILE_BASE+1)*16]
        checks['every_translated_atlas_pattern']=True
    def textured_pattern(c,tile_id):
        address=0x1000+tile_id*16 if tile_id<128 else 0x0800+(tile_id-128)*16
        return bytes(c.vram[0][address:address+16]),bytes(c.vram[1][address:address+16])
    if b.SLIM_DISPLAY and b.TEXTURED_WALLS:
        # The kernel composed blind (LCD off, as enter_world does) for far
        # walls inside the self-mirrored centre tile, a seam of two faces with
        # a decorated pixel, and a full-height wall whose 160 patterns lap the
        # 96-slot ring and cross the VRAM half: every pattern must land in
        # both banks exactly as the reference kernel composes it.
        c=boot();c.ime=False;c.write8(0xff40,0);c.write8(b.SIM_READY,0)
        scenes=[]
        for pattern in ((57,)*8,(58,)*8,(0,56,57,58,58,57,56,0)):
            tops=list(pattern)+[56]*152;styles=[0,1]*4+[0]*152
            scenes.append((tops,styles,[36]*160,[0]*160,[(x*5)&255 for x in range(160)]))
        scenes.append(([40]*160,[0]*80+[1]*80,[36]*77+[172]*83,[0]*40+[1]*60+[2]*60,[(x*3)&255 for x in range(160)]))
        scenes.append(([0]*160,[0,0,0,5]+[0]*156,[36]*160,[1]*160,[(x*17)&255 for x in range(160)]))
        for tops,styles,keys,surfaces,pixel_u in scenes:
            for x in range(160):
                c.write8(b.PIXEL_TOPS+x,tops[x]);c.write8(b.PIXEL_STYLES+x,styles[x]);c.write8(b.PIXEL_KEYS+x,keys[x])
                c.write8(b.PIXEL_SURFACE+x,surfaces[x]);c.write8(b.PIXEL_U+x,pixel_u[x])
            c.call_subroutine('render_view')
            dynamic,tilemap,count,overflow=b.reference_compose_textured_view(tops,styles,keys,surfaces,pixel_u)
            assert not overflow and c.read8(b.DYN_COUNT)==count and c.read8(b.DYN_STREAMED)==count and not c.hdma_active,(count,c.read8(b.DYN_COUNT))
            assert bytes(c.read8(b.VIEW_MAP+i) for i in range(b.VIEW_MAP_BYTES))==tilemap
            for tile_id in range(count):
                expected=dynamic[tile_id*16:tile_id*16+16]
                assert textured_pattern(c,tile_id)==(expected,expected),(tile_id,count)
        assert count==160
        checks['textured_blind_composition_ring_lap_and_vram_half']=True
    if b.SLIM_DISPLAY and not b.TEXTURED_WALLS:
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
    cases=((0,0),(8,0),(9,0),(0,16),(0,18),(0,32),(8,16),(9,16),(24,0),(25,0),(48,0),(49,0),(16,32),(17,32),(71,0),(72,0),(73,0),(40,32),(41,32),(96,0),(96,16),(96,32))
    if b.TEXTURED_WALLS:
        # The ring drains in chunks that stop at its wrap and the VRAM half;
        # counts beyond 96 reuse slots, so pattern i is expected from slot i mod 96.
        cases+=((97,0),(127,16),(128,0),(129,32),(160,0),(160,32))
    def expected_patterns(c,dyn):
        if not b.TEXTURED_WALLS:
            return bytes(c.read8(b.DYNAMIC_TILES+i) for i in range(dyn*16))
        return b''.join(bytes(c.read8(b.DYNAMIC_TILES+(i%b.DYNAMIC_RING_SLOTS)*16+j) for j in range(16)) for i in range(dyn))
    def hidden_patterns(c,bank,dyn):
        if not b.TEXTURED_WALLS:
            return bytes(c.vram[bank][0x1000:0x1000+dyn*16])
        return b''.join(textured_pattern(c,i)[bank] for i in range(dyn))
    for dyn,mask in cases:
        c=boot();c.write8(b.SIM_READY,0);c.write8(b.DYN_COUNT,dyn);c.write8(b.MASK_TILE_COUNT,mask)
        if b.TEXTURED_WALLS:c.write8(b.DYN_STREAMED,0);c.write8(b.DYN_INFLIGHT,0)
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
        if b.HDMA_STREAMING:
            # Everything hidden has already streamed by HBlank DMA: no
            # transfer is active, and the hidden bank/map hold the packet
            # before the tail's VBlank is even reached.
            assert not c.hdma_active and c.io[0x55]==0xFF
            hidden=old_page^1;offset=0x1800+hidden*0x400
            assert bytes(c.vram[0][offset:offset+b.VIEW_MAP_BYTES])==bytes(c.read8(b.VIEW_MAP+i) for i in range(b.VIEW_MAP_BYTES))
            assert hidden_patterns(c,hidden,dyn)==expected_patterns(c,dyn)
        c.run(until_presentations=1);event=c.commit_events[-1]
        map_blocks=b.VIEW_MAP_BYTES//16
        if b.HDMA_STREAMING:
            # HBlank: dynamic patterns and the map. VBlank: masks and attributes.
            assert event['hblank_blocks']==dyn+map_blocks and event['vblank_blocks']==mask+map_blocks,event
            assert all(e['vblank_safe_complete'] for e in event['events']) and event['vblank_safe'],event
            assert 144<=event['ly']<153,event
        else:
            assert event['blocks']==dyn+mask+48 and event['vblank_safe'],event
        assert not violations,violations[:5]
        page=c.read8(b.CURRENT_PAGE);offset=0x1800+page*0x400
        assert bytes(c.vram[0][offset:offset+b.VIEW_MAP_BYTES])==bytes(c.read8(b.VIEW_MAP+i) for i in range(b.VIEW_MAP_BYTES))
        assert bytes(c.vram[1][offset:offset+b.VIEW_MAP_BYTES])==bytes(c.read8(b.VIEW_ATTRIBUTES+i) for i in range(b.VIEW_MAP_BYTES))
        windows.append({'dynamic':dyn,'mask':mask,'blocks':event['blocks'],'commit_ly':event['ly'],'staged':event['staged']})
    checks['publication_cpu_and_dma_windows']=True
    if b.HDMA_STREAMING:
        # An HBlank block reads its source through SVBK. The streamed sources
        # are fixed WRAM precisely so that a simulation yield with bank 2
        # mapped cannot corrupt them: force bank 2 across every visible line
        # of a transfer and require the hidden bank to hold the exact bytes.
        c=boot();c.ime=False;c.write8(b.SIM_READY,0)
        for i in range(96*16):c.write8(b.DYNAMIC_TILES+i,(i*29+5)&255)
        for i in range(b.VIEW_MAP_BYTES):c.write8(b.VIEW_MAP+i,(i*7+1)&255)
        c.write8(b.DYN_COUNT,96);c.write8(b.DYN_STREAMED,0)
        if b.TEXTURED_WALLS:c.write8(b.DYN_INFLIGHT,0)
        # Spin on the idle poll alone with bank 2 mapped: it touches no
        # memory, so every block lands while the wrong WRAM bank is selected.
        c.call_subroutine('tex_stream_hblank' if b.TEXTURED_WALLS else 'stream_dynamic_tiles');assert c.hdma_active
        c.write8(0xff70,2);c.call_subroutine('stream_wait_idle');c.write8(0xff70,1)
        assert not c.hdma_active
        c.call_subroutine('stream_view_map');assert c.hdma_active
        c.write8(0xff70,2);c.call_subroutine('stream_wait_idle');c.write8(0xff70,1)
        hidden=c.read8(b.CURRENT_PAGE)^1;offset=0x1800+hidden*0x400
        assert bytes(c.vram[hidden][0x1000:0x1000+96*16])==bytes((i*29+5)&255 for i in range(96*16))
        assert bytes(c.vram[0][offset:offset+b.VIEW_MAP_BYTES])==bytes((i*7+1)&255 for i in range(b.VIEW_MAP_BYTES))
        assert c.read8(b.DYN_STREAMED)==96 and c.io[0x55]==0xFF
        c=boot();c.ime=False;c.write8(b.SIM_READY,0);c.write8(0xff40,0)
        transfers=len(c.gdma_events);c.call_subroutine('render_view')
        if b.TEXTURED_WALLS:
            # Composition with the LCD off (enter_world) flushes the ring into
            # both banks by general-purpose DMA as it goes: nothing is left
            # for the tail and no HBlank transfer was ever started.
            flushed=c.gdma_events[transfers:]
            assert flushed and all(e.get('kind')!='hdma' for e in flushed) and c.read8(b.DYN_STREAMED)==c.read8(b.DYN_COUNT) and not c.hdma_active
        else:
            # Composition with the LCD off (enter_world) never starts a transfer,
            # and the tail then streams everything the blind pass left behind.
            assert len(c.gdma_events)==transfers and c.read8(b.DYN_STREAMED)==0 and not c.hdma_active
        # Streaming during a real composition hands over every column's
        # patterns as it finishes: the tail's own transfer is a remainder.
        c=boot();c.ime=False;c.write8(b.SIM_READY,0);apply_diagnostic_camera(c,{'pose':(1152,3100,191)})
        c.call_subroutine('cast_all');transfers=len(c.gdma_events);c.call_subroutine('render_view')
        chained=[e for e in c.gdma_events[transfers:] if e.get('kind')=='hdma']
        assert chained and sum(e['blocks'] for e in chained)==c.read8(b.DYN_STREAMED)<=c.read8(b.DYN_COUNT)
        c.call_subroutine('upload_hidden_page')
        event=c.commit_events[-1];assert event['vblank_safe'] and event['hblank_blocks']==c.read8(b.DYN_COUNT)+b.VIEW_MAP_BYTES//16
        checks['hblank_streaming_bank_isolation_and_chaining']=True
    output.mkdir(parents=True,exist_ok=True)
    for index,pose in enumerate(((1152,3456,192),(1408,3328,192),(1152,3136,192),(1152,3100,191),(1152,3100,255),(1408,3200,0))):
        c=boot();c.write8(b.SIM_READY,0);apply_diagnostic_camera(c,{'pose':pose});c.run(until_presentations=2)
        validate_frame(c);im=c.render_screen();path=output/f'pose-{index}.png';im.save(path);im.resize((640,576),resample=0).save(output/f'pose-{index}-4x.png')
        captures.append({'file':path.name,'pose':pose,'pixels_sha256':hashlib.sha256(im.tobytes()).hexdigest()})
        if snapshots is not None:captures[-1]['snapshot']=snapshots.observe(f'pose-{index}',im)
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
    # The HUD's art contract is data: which portrait and status each state
    # selects, and which HUD pixels every state must leave alone. The
    # packet/publication mechanics below stay code because they are invariants.
    fixture=hud_fixture()
    for health,hurt,tick,portrait in fixture['portraits']['cases']:
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
        for i in range(b.MAX_ACTORS):c.write8(b.ENTITY_SLOTS+i*16+4,b.SENTINEL_DORMANT)
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
    for health,done,exit_active,status in fixture['status']['cases']:
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
    if 'chassis_rows' in fixture:
        # Read published VRAM, including both pages and every digit, portrait
        # and terminal caption, across every state the fixture lists: the
        # dynamic tiles under the HUD row must retain the static divider, and
        # every chassis pixel, point and clear span the fixture pins must hold.
        divider=bytes.fromhex(fixture['divider']['first_row_bytes'])
        def hud_pixel(page,x,y):
            tile=c.vram[0][page+(b.VIEW_ROWS+y//8)*32+x//8]
            address=tile*16+(y%8)*2;bit=7-x%8
            return ((c.vram[0][address]>>bit)&1)|(((c.vram[0][address+1]>>bit)&1)<<1)
        for health,hurt,tick,done in fixture['states']['health_ladder']+fixture['states']['expressions']:
            c.write8(b.PLAYER_HEALTH,health);c.write8(b.HURT_ACTIVE,hurt)
            c.write16(b.FRAME_TICK,tick);c.write8(b.LEVEL_COMPLETE,done)
            c.call_subroutine('prepare_hud_tiles');c.call_subroutine('update_hud_tiles')
            state=(health,hurt,tick,done)
            for page in (0x1800,0x1C00):
                for column in range(20):
                    tile=c.vram[0][page+b.VIEW_ROWS*32+column]
                    assert bytes(c.vram[0][tile*16:tile*16+2])==divider,(state,page,column,fixture['divider']['why'])
                for y,row in fixture['chassis_rows'].items():
                    actual=''.join(str(hud_pixel(page,x,int(y))) for x in range(160))
                    assert actual==row,(state,page,'HUD row',y,actual,row)
                for point in fixture['points']:
                    assert hud_pixel(page,point['x'],point['y'])==point['expected'],(state,page,point['why'])
                for span in fixture['clear_spans']:
                    assert all(hud_pixel(page,x,span['y'])==span['expected'] for x in range(*span['x'])),(state,page,span['why'])
        checks['continuous_divider_all_dynamic_states_and_both_maps']=True
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
        for i in range(b.MAX_ACTORS):c.write8(b.ENTITY_SLOTS+i*16+14,3)
        c.write16(b.SIM_TICK,65535);c.call_subroutine('simulation_tick')
        c.write16(b.SIM_TICK,0);c.call_subroutine('simulation_tick')
        assert c.read8(b.SHOT_ACTIVE)==0 and c.read8(b.ACTOR_REACTION)==0
        assert all(c.read8(b.ENTITY_SLOTS+i*16+14)==0 for i in range(b.MAX_ACTORS))
        assert c.read8(b.FLASH)==9
    checks['terminal_state_wrap_cannot_replay_cosmetics']=True
    result={'schema':'sable.qualification.v1','rom_sha256':hashlib.sha256(rom).hexdigest(),'configuration':b.RENDER_CONFIG,'checks':checks,'assets':evidence(),'publication_windows':windows,'captures':captures,'physical_hardware_tested':False,'passed':all(checks.values())}
    if snapshots is not None:result['snapshot']=snapshots.report()
    (output/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if snapshots is not None:result['snapshot']=snapshots.finish()  # raises in check mode when a pose differs
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=b.BUILD/'sable-v2/checks')
    p.add_argument('--snapshot-mode',choices=('check','record','none'),default='check');args=p.parse_args()
    check(args.output_dir,None if args.snapshot_mode=='none' else args.snapshot_mode)
