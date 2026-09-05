"""Four bounded Sentinel slots; one proven actor implementation reused safely."""
from .layout import *  # noqa: F401,F403


def actor_records() -> bytes:
    records = bytearray(MAX_ACTORS * 16)
    for index in range(MAX_ACTORS):
        records[index * 16 + 4] = SENTINEL_DEAD
    for index, entity in enumerate(ACTIVE_LEVEL.entities):
        records[index * 16:index * 16 + 6] = bytes((entity.x_q8 & 255, entity.x_q8 >> 8,
                                                    entity.y_q8 & 255, entity.y_q8 >> 8,
                                                    SENTINEL_DORMANT, entity.health))
    return bytes(records)


def emit_actors(a: Assembler) -> None:
    a.label("init_actors")
    a.ld_rr_label("hl", "actor_records"); a.ld_rr_nn("de", ENTITY_SLOTS); a.ld_rr_nn("bc", MAX_ACTORS * 16); a.call("copy_bc")
    a.ld_r_n("a", len(ACTIVE_LEVEL.entities)); a.ld_abs_a(ACTOR_COUNT)
    a.xor_r("a"); a.ld_abs_a(ENTITY_SLOT); a.jp("actor_load")

    a.label("actor_pointer")
    a.ld_a_abs(ENTITY_SLOT); a.cb("swap", "a"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    a.ld_rr_nn("de", ENTITY_SLOTS); a.add_hl_rr("de"); a.ret()
    a.label("actor_save")
    a.call("actor_pointer"); a.ld_r_r("d", "h"); a.ld_r_r("e", "l")
    a.ld_rr_nn("hl", SENTINEL_XL); a.ld_rr_nn("bc", 10); a.call("copy_bc")
    for address in (PICKUP_ACTIVE, PICKUP_COLLECTED):
        a.ld_a_abs(address); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()
    a.label("actor_load")
    a.call("actor_pointer"); a.ld_rr_nn("de", SENTINEL_XL); a.ld_rr_nn("bc", 10); a.call("copy_bc")
    for address in (PICKUP_ACTIVE, PICKUP_COLLECTED):
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
    a.ld_a_abs(SIM_TICK); a.and_n(AI_TICK_INTERVAL - 1); a.jr("actor_update_store", "nz")
    a.ld_a_abs(SENTINEL_STATE); a.cp_n(SENTINEL_DEAD); a.jr("actor_update_store", "z")
    a.call("sentinel_ai_tick")
    a.label("actor_update_store"); a.call("actor_save"); a.call("actor_next"); a.jr("actor_update_loop", "nz")
    a.call("check_all_actors_dead"); a.jp("restore_primary_actor")

    a.label("project_actor_depths")
    a.call("save_primary_actor")
    a.label("actor_project_loop")
    a.call("actor_load"); a.call("project_sentinel")
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
