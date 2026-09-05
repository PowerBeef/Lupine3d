"""Cosmetic animation clocks. Live accepted ticks, immutable render packets.

D77A..D789 already belong to the copied world span. Actor record bytes 12..15
own their reaction clock/kind. No animation state changes gameplay decisions.
"""
from .layout import *


def stamp(a, address):
    for i in (0,1):a.ld_a_abs(SIM_TICK+i);a.ld_abs_a(address+i)


def age(a, address, clock=SIM_TICK):
    # Unsigned wrap-safe difference HL; clobbers A/B/HL. Reactions are expired
    # every simulation tick, so a full 16-bit wrap can never resurrect them.
    a.ld_a_abs(address);a.ld_r_r('b','a');a.ld_a_abs(clock);a.sub_r('b');a.ld_r_r('l','a')
    a.ld_a_abs(address+1);a.ld_r_r('b','a');a.ld_a_abs(clock+1);a.sbc_a_r('b');a.ld_r_r('h','a')


def emit_animation(a):
    if not (SABLE_ART or COMPACT_DISPLAY):return
    a.label('init_art_clocks')
    a.xor_r('a')
    for address in range(SHOT_TICK,ART_STATE_END):a.ld_abs_a(address)
    stamp(a,HINT_TICK);a.ld_r_n('a',1);a.ld_abs_a(HINT_ACTIVE);a.ret()
    a.label('stop_art_clocks')
    # Terminal gameplay ticks do not run actor updates. Clear ownership here
    # so a full 16-bit tick wrap cannot replay a corpse or weapon reaction.
    # FLASH remains pending until its existing snapshot acknowledgement.
    a.xor_r('a')
    for address in (SHOT_ACTIVE,HURT_ACTIVE,HINT_ACTIVE,ACTOR_REACTION,
                    *(ENTITY_SLOTS+i*16+14 for i in range(MAX_ACTORS))):
        a.ld_abs_a(address)
    a.ret()
    a.label('advance_art_clocks')
    for name,tick,active,limit in [('shot',SHOT_TICK,SHOT_ACTIVE,24),('hurt',HURT_TICK,HURT_ACTIVE,8),('hint',HINT_TICK,HINT_ACTIVE,180)]:
        age(a,tick);a.ld_r_r('a','h');a.or_r('a');a.jr(name+'_expire','nz')
        a.ld_r_r('a','l');a.cp_n(limit);a.jr(name+'_clock_done','c')
        a.label(name+'_expire');a.xor_r('a');a.ld_abs_a(active);a.label(name+'_clock_done')
    a.ret()
    a.label('stamp_shot');stamp(a,SHOT_TICK);a.ld_r_n('a',1);a.ld_abs_a(SHOT_ACTIVE);a.ret()
    a.label('stamp_player_hurt');stamp(a,HURT_TICK);a.ld_r_n('a',1);a.ld_abs_a(HURT_ACTIVE);a.ret()
    a.label('stamp_actor_reaction') # A=1 attack,2 hurt,3 death
    a.ld_abs_a(ACTOR_REACTION);stamp(a,ACTOR_REACTION_TICK);a.ret()
    a.label('expire_actor_reaction')
    age(a,ACTOR_REACTION_TICK);a.ld_r_r('a','h');a.or_r('a');a.jr('actor_reaction_expire','nz')
    a.ld_r_r('a','l');a.cp_n(36);a.ret('c')
    a.label('actor_reaction_expire');a.xor_r('a');a.ld_abs_a(ACTOR_REACTION);a.ret()

    a.label('select_actor_animation')
    if not ART_ANIMATION:
        a.xor_r('a');a.ld_abs_a(SENTINEL_ANIM);a.ret()
    else:
        age(a,ACTOR_REACTION_TICK,FRAME_TICK)
        a.ld_r_r('a','h');a.or_r('a');a.jr('actor_cycle','nz')
        a.ld_a_abs(ACTOR_REACTION);a.cp_n(3);a.jr('actor_death_cel','z')
        a.ld_r_r('a','l');a.cp_n(8);a.jr('actor_cycle','nc')
        a.ld_a_abs(ACTOR_REACTION);a.cp_n(2);a.ld_r_n('a',8);a.jr('actor_cel_ready','z')
        a.ld_a_abs(ACTOR_REACTION);a.cp_n(1);a.jr('actor_cycle','nz')
        a.ld_r_r('a','l');a.cb('srl','a');a.cb('srl','a');a.add_a_n(6);a.jr('actor_cel_ready')
        a.label('actor_death_cel');a.ld_r_r('a','l');a.cp_n(12);a.ld_r_n('a',9);a.jr('actor_cel_ready','c')
        a.ld_r_r('a','l');a.cp_n(24);a.ld_r_n('a',10);a.jr('actor_cel_ready','c');a.ld_r_n('a',11);a.jr('actor_cel_ready')
        a.label('actor_cycle');a.ld_a_abs(SENTINEL_STATE);a.cp_n(SENTINEL_DORMANT);a.jr('actor_idle','z');a.cp_n(SENTINEL_ATTACK);a.jr('actor_idle','z')
        a.ld_a_abs(FRAME_TICK)
        for _ in range(3):a.cb('srl','a')
        a.and_n(3);a.add_a_n(2);a.jr('actor_cel_ready')
        a.label('actor_idle');a.ld_a_abs(FRAME_TICK)
        for _ in range(5):a.cb('srl','a')
        a.and_n(1)
        a.label('actor_cel_ready');a.ld_abs_a(SENTINEL_ANIM);a.ret()

    a.label('animate_weapon')
    if not SABLE_ART:a.ret()
    else:
        a.ld_r_n('c',0)
        if ART_ANIMATION:
            a.ld_a_abs(FLASH);a.or_r('a');a.jr('weapon_pending_flash','nz')
            a.ld_a_abs(SHOT_ACTIVE);a.or_r('a');a.jr('weapon_frame_ready','z')
            age(a,SHOT_TICK,FRAME_TICK);a.ld_r_r('a','h');a.or_r('a');a.jr('weapon_frame_ready','nz')
            for limit,cel in ((4,1),(10,2),(16,3),(24,4)):
                a.ld_r_r('a','l');a.cp_n(limit);a.ld_r_n('c',cel);a.jr('weapon_frame_ready','c')
            a.ld_r_n('c',0);a.jr('weapon_frame_ready')
            a.label('weapon_pending_flash');a.ld_r_n('c',1)
        a.label('weapon_frame_ready');a.ld_r_r('a','c');a.cb('swap','a');a.add_a_n(WEAPON_TILE_BASE)
        for index in range(8):
            a.ld_abs_a(OAM_SHADOW+index*4+2);a.add_a_n(2)
        a.ld_r_n('a',1);a.ld_abs_a(OAM_DIRTY)
        a.ld_a_abs(FRAME_TICK);a.and_n(1);a.add_a_r('a');a.add_a_n(MUZZLE_TILE);a.ld_abs_a(OAM_SHADOW+9*4+2);a.ret()

    a.label('prepare_compact_hud')
    if not COMPACT_DISPLAY:a.ret()
    else:
        from .artwork import hud_assets
        records=hud_assets()[3]
        a.ld_r_n('b',0)
        if ART_ANIMATION:
            # Two late-cycle ticks keep the initial portrait alert. Both branch
            # paths still cost twelve T-cycles (JR taken vs JR plus INC).
            a.ld_a_abs(FRAME_TICK);a.and_n(63);a.cp_n(62 if SLIM_DISPLAY else 4);a.jr('portrait_not_blink','c' if SLIM_DISPLAY else 'nc');a.inc_r('b')
            a.label('portrait_not_blink');a.ld_a_abs(HURT_ACTIVE);a.or_r('a');a.jr('portrait_not_hurt','z');a.ld_r_n('b',2);a.label('portrait_not_hurt')
        a.ld_a_abs(PLAYER_HEALTH);a.or_r('a');a.jr('portrait_alive','nz');a.ld_r_n('b',3);a.label('portrait_alive')
        a.ld_r_r('a','b');a.add_a_r('a');
        if SLIM_DISPLAY:a.add_a_r('b')
        a.add_a_r('a');a.ld_r_r('e','a');a.ld_r_n('d',0);a.ld_rr_label('hl','portrait_records');a.add_hl_rr('de')
        for i in range(HUD_PORTRAIT_TILES):a.ldi_a_hl();a.ld_abs_a(HUD_PACKET+HUD_PORTRAIT_OFFSET+i)
        # Controls/help do not belong in the gameplay HUD. No interaction
        # ray probe or hint packet is prepared here.
        a.ret()
        a.label('portrait_records');a.bytes(bytes(v for i in range(4) for v in records['portrait'+str(i)]))
