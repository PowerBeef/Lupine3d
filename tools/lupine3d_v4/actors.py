"""Four bounded Sentinel slots; one proven actor implementation reused safely."""
from .layout import *  # noqa: F401,F403
from .levels import ENTITY_KIND_IDS


def actor_records(level=None) -> bytes:
    level = level or ACTIVE_LEVEL
    records = bytearray(MAX_ACTORS * 16)
    for index in range(MAX_ACTORS):
        records[index * 16 + 4] = SENTINEL_DEAD
    for index, entity in enumerate(level.entities):
        records[index * 16:index * 16 + 6] = bytes((entity.x_q8 & 255, entity.x_q8 >> 8,
                                                    entity.y_q8 & 255, entity.y_q8 >> 8,
                                                    SENTINEL_DORMANT, entity.health))
        records[index * 16 + ACTOR_KIND_OFFSET] = ENTITY_KIND_IDS[entity.kind]
    return bytes(records)


def emit_actors(a: Assembler) -> None:
    a.label("init_actors")
    # Slot contents come from the selected level's bank; ACTOR_COUNT was
    # already read out of that level's header by load_level.
    a.ld_a_abs(LEVEL_BANK); a.ld_abs_a(0x2000)
    a.ld_rr_nn("hl", LEVEL_ACTOR_OFFSET); add_level_page(a)
    a.ld_rr_nn("de", ENTITY_SLOTS); a.ld_rr_nn("bc", MAX_ACTORS * 16); a.call("copy_bc")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    # Patrol headings are not authored: each slot starts on its own compass
    # point, so a room full of actors does not set off as one column.
    for index in range(MAX_ACTORS):
        a.ld_r_n("a", index); a.ld_abs_a(ACTOR_PATROL + index)
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT); a.jp("actor_load")

    a.label("actor_pointer")
    a.ld_a_abs(ENTITY_SLOT); a.cb("swap", "a"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    a.ld_rr_nn("de", ENTITY_SLOTS); a.add_hl_rr("de"); a.ret()
    # Ten fixed bytes each way, inline: a slot is loaded and stored about
    # sixteen times per update, and copy_bc's prologue outweighs the copy.
    a.label("actor_save")
    a.call("actor_pointer"); a.ld_r_r("d", "h"); a.ld_r_r("e", "l")
    a.ld_rr_nn("hl", SENTINEL_XL)
    for _ in range(10): a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    for address in ACTOR_SLOT_TAIL:
        a.ld_a_abs(address); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()
    a.label("actor_load")
    a.call("actor_pointer"); a.ld_rr_nn("de", SENTINEL_XL)
    for _ in range(10): a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    for address in ACTOR_SLOT_TAIL:
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ret()
    a.label("save_primary_actor")
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT); a.jp("actor_save")
    a.label("restore_primary_actor")
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT); a.jp("actor_load")
    a.label("actor_next")
    a.ld_a_abs(ENTITY_SLOT); a.inc_r("a"); a.ld_abs_a(ENTITY_SLOT); a.ld_r_r("b", "a")
    a.ld_a_abs(ACTOR_COUNT); a.cp_r("b"); a.ret()

    a.label("check_all_actors_dead")
    a.ld_r_n("a", 1); a.ld_abs_a(EXIT_ACTIVE)
    for index in range(MAX_ACTORS):
        a.ld_a_abs(ACTOR_COUNT); a.cp_n(index + 1); a.ret("c")
        a.ld_a_abs(ENTITY_SLOTS + index * 16 + 4); a.cp_n(SENTINEL_DEAD); a.jr("actor_exit_locked", "nz")
    a.ret()
    a.label("actor_exit_locked"); a.xor_r("a"); a.ld_abs_a(EXIT_ACTIVE); a.ret()

    a.label("update_actors")
    a.call("save_primary_actor")
    a.label("actor_update_loop")
    a.call("actor_load"); a.call("collect_pickup_and_exit")
    if SABLE_ART: a.call("expire_actor_reaction")
    a.ld_a_abs(SIM_TICK); a.and_n(AI_TICK_INTERVAL - 1); a.jr("actor_update_store", "nz")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.jr("actor_update_store", "z")
    a.call("sentinel_ai_tick")
    a.label("actor_update_store"); a.call("actor_save"); a.call("actor_next"); a.jr("actor_update_loop", "nz")
    a.call("check_all_actors_dead"); a.jp("restore_primary_actor")

    # What project_sentinel leaves for the draw paths, kept per slot so the
    # draw pass restores it instead of projecting the same inputs again. The
    # LOD hysteresis is idempotent for a repeated projection (a second call
    # with the first call's history returns the first call's LOD), so the
    # restored record is exactly what the second projection would produce.
    PROJECTION_RECORD = ((SENTINEL_VISIBLE, 4), (ENTITY_FOOT_Y, 1), (ENTITY_SCREEN_LEFT, 2), (MASK_BITS, 1))
    assert sum(count for _, count in PROJECTION_RECORD) == ACTOR_PROJECTION_BYTES
    a.label("actor_projection_pointer")   # HL -> this slot's record
    a.ld_a_abs(ENTITY_SLOT)
    for _ in range(ACTOR_PROJECTION_BYTES.bit_length() - 1): a.add_a_r("a")
    a.add_a_n(ACTOR_PROJECTION & 255); a.ld_r_r("l", "a"); a.ld_r_n("h", ACTOR_PROJECTION >> 8); a.ret()

    a.label("cache_actor_projection")
    a.call("actor_projection_pointer"); a.ld_r_r("d", "h"); a.ld_r_r("e", "l")
    for address, count in PROJECTION_RECORD:
        a.ld_rr_nn("hl", address)
        for _ in range(count): a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ld_a_abs(ENTITY_SLOT); a.add_a_n(ACTOR_PROJECTED & 255); a.ld_r_r("l", "a"); a.ld_r_n("h", ACTOR_PROJECTED >> 8)
    a.ld_r_n("a", 1); a.ld_hl_a(); a.ret()

    a.label("project_sentinel_cached")   # this frame's record if the depth pass made one
    a.ld_a_abs(ENTITY_SLOT); a.add_a_n(ACTOR_PROJECTED & 255); a.ld_r_r("l", "a"); a.ld_r_n("h", ACTOR_PROJECTED >> 8)
    a.ld_a_hl(); a.or_r("a"); a.jp("project_sentinel", "z")
    a.call("actor_projection_pointer")
    for address, count in PROJECTION_RECORD:
        a.ld_rr_nn("de", address)
        for _ in range(count): a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()

    a.label("project_actor_depths")
    a.call("save_primary_actor")
    a.label("actor_project_loop")
    a.call("actor_load"); a.call("project_sentinel"); a.call("cache_actor_projection")
    a.ld_r_n("b", 255); a.ld_a_abs(SENTINEL_VISIBLE); a.or_r("a"); a.jr("actor_depth_ready", "z")
    a.ld_a_abs(SENTINEL_DEPTH); a.ld_r_r("b", "a")
    a.label("actor_depth_ready")
    a.ld_a_abs(ENTITY_SLOT); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", ACTOR_DEPTHS); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ld_hl_a()
    a.call("actor_next"); a.jr("actor_project_loop", "nz")
    a.ret()

    a.label("select_nearest_actor")
    a.ld_r_n("a", 255); a.ld_abs_a(ACTOR_BEST); a.ld_abs_a(ACTOR_BEST_DEPTH)
    for index in range(MAX_ACTORS):
        skip = f"actor_select_{index}_skip"
        a.ld_a_abs(ACTOR_COUNT); a.cp_n(index + 1); a.ret("c")
        a.ld_a_abs(ACTOR_DEPTHS + index); a.ld_r_r("b", "a"); a.ld_a_abs(ACTOR_BEST_DEPTH); a.cp_r("b"); a.jr(skip, "c"); a.jr(skip, "z")
        a.ld_r_r("a", "b"); a.ld_abs_a(ACTOR_BEST_DEPTH); a.ld_r_n("a", index); a.ld_abs_a(ACTOR_BEST)
        a.label(skip)
    a.ret()

    a.label("render_actor_slots")
    a.call("project_actor_depths")
    a.ld_r_n("a", MAX_ACTORS); a.ld_abs_a(ACTOR_PASS)
    a.label("actor_draw_loop")
    a.call("select_nearest_actor"); a.ld_a_abs(ACTOR_BEST); a.cp_n(255); a.jp("restore_primary_actor", "z")
    a.ld_abs_a(ENTITY_SLOT); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", ACTOR_DEPTHS); a.add_hl_rr("de"); a.ld_hl_n(255)
    a.call("actor_load"); a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.jr("actor_draw_pickup", "z")
    a.call("render_sentinel_actor"); a.jr("actor_draw_next")
    a.label("actor_draw_pickup"); a.call("render_dropped_pickup")
    a.label("actor_draw_next")
    a.ld_a_abs(ACTOR_PASS); a.dec_r("a"); a.ld_abs_a(ACTOR_PASS); a.jr("actor_draw_loop", "nz")
    a.jp("restore_primary_actor")

    a.label("player_fire_hitscan")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.ret("z")
    a.call("project_actor_depths")
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT)
    a.label("actor_aim_filter")
    a.call("actor_load"); a.call("project_sentinel")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.jr("actor_aim_reject", "z")
    a.ld_a_abs(SENTINEL_SCREEN_X); a.cp_n(72); a.jr("actor_aim_reject", "c"); a.cp_n(89); a.jr("actor_aim_accept", "c")
    a.label("actor_aim_reject")
    a.ld_a_abs(ENTITY_SLOT); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", ACTOR_DEPTHS); a.add_hl_rr("de"); a.ld_hl_n(255)
    a.jr("actor_aim_next")
    a.label("actor_aim_accept")
    # Visibility is a render snapshot, not permission to hit. Only current
    # aim/depth nominate the target; player_fire_single performs the LOS cast.
    a.ld_a_abs(ENTITY_SLOT); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", ACTOR_DEPTHS); a.add_hl_rr("de")
    a.ld_a_abs(SENTINEL_DEPTH); a.ld_hl_a()
    a.label("actor_aim_next"); a.call("actor_next"); a.jr("actor_aim_filter", "nz")
    a.call("select_nearest_actor"); a.ld_a_abs(ACTOR_BEST); a.cp_n(255); a.jp("restore_primary_actor", "z")
    a.ld_abs_a(ENTITY_SLOT); a.call("actor_load"); a.call("player_fire_single"); a.call("actor_save")
    a.call("check_all_actors_dead"); a.jp("restore_primary_actor")

    if SABLE_ART and ART_ANIMATION:
        a.label("render_cosmetic_deaths")
        a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT)
        a.label("corpse_loop"); a.call("actor_load")
        a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.jr("corpse_next","nz")
        a.ld_a_abs(ACTOR_REACTION); a.cp_n(3); a.jr("corpse_next","nz")
        from .animation import age
        age(a,ACTOR_REACTION_TICK,FRAME_TICK)
        a.ld_r_r("a","h"); a.or_r("a"); a.jr("corpse_next","nz")
        a.ld_r_r("a","l"); a.cp_n(36); a.jr("corpse_next","nc")
        a.call("render_sentinel_actor")
        a.label("corpse_next"); a.call("actor_next"); a.jr("corpse_loop","nz")
        a.jp("restore_primary_actor")
