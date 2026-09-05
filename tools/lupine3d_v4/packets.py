"""Certified four-anchor traversal with a bounded two-sibling split stack.

The interval is E=[Nx*minY-Ny*maxX, Nx*maxY-Ny*minX]. X is shared only
when Emax<=0; Y only when Emin>0. A split resumes from the same certified
cell. Door entry delegates each ray to the existing exact finite-panel path.
"""
from .layout import *
from .precision import q14_direction
from .resources import make_tables

PK_FIRST = PACKET_WORKSPACE
PK_COUNT = PACKET_WORKSPACE+1
PK_X,PK_Y = PACKET_WORKSPACE+2,PACKET_WORKSPACE+3
PK_NX,PK_NY = PACKET_WORKSPACE+4,PACKET_WORKSPACE+6
PK_CROSS = PACKET_WORKSPACE+8
PK_SX,PK_SY = PACKET_WORKSPACE+9,PACKET_WORKSPACE+10
PK_AXIS = PACKET_WORKSPACE+11
PK_EMIN,PK_EMAX = PACKET_WORKSPACE+12,PACKET_WORKSPACE+16
PK_MINX,PK_MAXX = PACKET_WORKSPACE+20,PACKET_WORKSPACE+22
PK_MINY,PK_MAXY = PACKET_WORKSPACE+24,PACKET_WORKSPACE+26
PK_MATERIAL,PK_DISTANCE = PACKET_WORKSPACE+28,PACKET_WORKSPACE+29
PK_STACK = PACKET_WORKSPACE+31


def packet_record(yaw,group):
    assert 0 <= yaw < 256 and 0 <= group < 10
    first = group*8
    vectors = [q14_direction(yaw,first+i*2) for i in range(4)]
    signs = [(1 if x>0 else 255 if x<0 else 0,1 if y>0 else 255 if y<0 else 0) for x,y in vectors]
    tables = make_tables()
    coarse = []
    for index in range(first,first+8,2):
        offset = int.from_bytes(tables["ray_offsets"][index*2:index*2+2],"little",signed=True)
        direction = (yaw*4+offset)%1024
        coarse.append(tables["ray_packed"][direction*4:direction*4+4])
    valid = len(set(signs)) == 1 and all(x and y for x,y in signs) and all(row[0] and row[1] for row in coarse)
    bounds = [min(abs(v[axis]) for v in vectors) if end==0 else max(abs(v[axis]) for v in vectors)
              for axis in (0,1) for end in (0,1)]
    return b"".join(value.to_bytes(2,"little") for value in bounds)+bytes((*signs[0],first,4,int(valid),0,0,0))


def emit_packets(a: Assembler):
    if not ANCHOR_PACKETS: return
    loader = "load_ray_setup_prepared" if CAMERA_SETUP else "load_ray_setup"
    a.label("cast_anchor_packet")
    a.label("packet_setup")
    a.xor_r("a"); a.ld_abs_a(PK_STACK); a.ld_abs_a(PK_CROSS)
    if PACKET_BOUNDS_REUSE: a.ld_abs_a(PK_MATERIAL)
    a.ld_a_abs(PLAYER_XH); a.ld_abs_a(PK_X); a.ld_a_abs(PLAYER_YH); a.ld_abs_a(PK_Y)
    # Records 241..250 are the only padding consumed by this ABI.
    a.ld_a_abs(ANGLE); a.ld_r_r("b","a"); a.cb("srl","a"); a.cb("srl","a")
    a.add_a_n(RAY_SETUP_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_a_abs(ADAPTIVE_INDEX)
    for _ in range(3): a.cb("srl","a")
    a.inc_r("a"); a.cb("swap","a"); a.ld_r_r("l","a")
    a.ld_r_r("a","b"); a.and_n(3); a.cb("swap","a"); a.or_n(0x4F); a.ld_r_r("h","a")
    a.ld_rr_nn("de",PK_MINX); a.ld_r_n("b",8)
    a.label("packet_load_bounds")
    a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de"); a.dec_r("b"); a.jr("packet_load_bounds","nz")
    for address in (PK_SX,PK_SY,PK_FIRST,PK_COUNT,PK_AXIS): a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_r_n("a",1); a.ld_abs_a(0x2000)
    a.ld_a_abs(PK_AXIS); a.or_r("a"); a.jp("packet_generic_all","z")
    a.call("packet_read_cell"); a.cp_n(3); a.jp("packet_generic_all","z")
    for name,step,positive,negative,target in (("x",PK_SX,FRAME_X_POS_L,FRAME_X_NEG_L,PK_NX),
                                             ("y",PK_SY,FRAME_Y_POS_L,FRAME_Y_NEG_L,PK_NY)):
        a.ld_a_abs(step); a.cp_n(1); a.ld_rr_nn("hl",positive); a.jr("packet_initial_"+name,"z")
        a.ld_rr_nn("hl",negative); a.label("packet_initial_"+name)
        a.ldi_a_hl(); a.ld_abs_a(target); a.ld_a_hl(); a.ld_abs_a(target+1)
    a.jp("packet_initialize_bounds")

    a.label("packet_rebound")
    a.ld_a_abs(PK_COUNT); a.cp_n(1); a.jp("packet_scalar_all","z")
    # Within a certified quadrant the component magnitudes are monotone.
    # Split bounds therefore need only the first and last prepared vectors.
    a.ld_a_abs(PK_FIRST); a.ld_abs_a(Q14_RECORD); a.call(loader)
    for source,targets in ((Q14_X,(PK_MINX,PK_MAXX)),(Q14_Y,(PK_MINY,PK_MAXY))):
        for byte in range(2):
            a.ld_a_abs(source+byte)
            for target in targets: a.ld_abs_a(target+byte)
    a.ld_a_abs(PK_COUNT); a.dec_r("a"); a.add_a_r("a"); a.ld_r_r("b","a")
    a.ld_a_abs(PK_FIRST); a.add_a_r("b"); a.ld_abs_a(Q14_RECORD); a.call(loader)
    a.ld_a_abs(PK_SX); a.ld_r_r("b","a"); a.ld_a_abs(PK_SY); a.cp_r("b"); a.jr("packet_magnitudes_decreasing_x","z")
    for byte in range(2):
        a.ld_a_abs(Q14_X+byte); a.ld_abs_a(PK_MAXX+byte)
        a.ld_a_abs(Q14_Y+byte); a.ld_abs_a(PK_MINY+byte)
    a.jr("packet_initialize_bounds")
    a.label("packet_magnitudes_decreasing_x")
    for byte in range(2):
        a.ld_a_abs(Q14_X+byte); a.ld_abs_a(PK_MINX+byte)
        a.ld_a_abs(Q14_Y+byte); a.ld_abs_a(PK_MAXY+byte)

    a.label("packet_initialize_bounds")
    for dest,y_bound,x_bound in ((PK_EMIN,PK_MINY,PK_MAXX),(PK_EMAX,PK_MAXY,PK_MINX)):
        if PACKET_BOUNDS_REUSE:
            # A four-to-two split retains one endpoint and its exact error.
            # PK_MATERIAL is left=1/right=2 ownership until a wall hit.
            a.call("packet_reused_bound")
            a.cp_n(1 if dest == PK_EMIN else 2); a.jp(f"packet_bound_ready_{dest}","z")
        load_hl_abs(a,PK_NX,PK_NX+1)
        a.ld_a_abs(y_bound); a.ld_r_r("e","a"); a.ld_a_abs(y_bound+1); a.ld_r_r("d","a")
        a.call("q14_multiply_u16")
        for byte in range(4): a.ld_a_abs(Q14_PRODUCT+byte); a.ld_abs_a(dest+byte)
        load_hl_abs(a,PK_NY,PK_NY+1)
        a.ld_a_abs(x_bound); a.ld_r_r("e","a"); a.ld_a_abs(x_bound+1); a.ld_r_r("d","a")
        a.call("q14_multiply_u16")
        for byte in range(4):
            a.ld_a_abs(Q14_PRODUCT+byte); a.ld_r_r("b","a"); a.ld_a_abs(dest+byte)
            if byte: a.sbc_a_r("b")
            else: a.sub_r("b")
            a.ld_abs_a(dest+byte)
        if PACKET_BOUNDS_REUSE: a.label(f"packet_bound_ready_{dest}")
    if PACKET_BOUNDS_REUSE:
        a.xor_r("a"); a.ld_abs_a(PK_MATERIAL)

    a.label("packet_bounds")
    a.ld_a_abs(PK_EMAX+3); a.cb("bit","a",7); a.jp("packet_step_x","nz")
    a.ld_r_r("b","a")
    for byte in range(3): a.ld_a_abs(PK_EMAX+byte); a.or_r("b"); a.ld_r_r("b","a")
    a.jp("packet_step_x","z")
    a.ld_a_abs(PK_EMIN+3); a.cb("bit","a",7); a.jp("packet_split","nz")
    a.ld_r_r("b","a")
    for byte in range(3): a.ld_a_abs(PK_EMIN+byte); a.or_r("b"); a.ld_r_r("b","a")
    a.jp("packet_split","z"); a.jp("packet_step_y")

    for name,axis,cell,step,distance in (("x",0,PK_X,PK_SX,PK_NX),("y",1,PK_Y,PK_SY,PK_NY)):
        a.label("packet_step_"+name)
        a.ld_r_n("a",axis); a.ld_abs_a(PK_AXIS)
        a.ld_a_abs(step); a.ld_r_r("b","a"); a.ld_a_abs(cell); a.add_a_r("b"); a.ld_abs_a(cell)
        for byte in range(2): a.ld_a_abs(distance+byte); a.ld_abs_a(PK_DISTANCE+byte)
        a.jp("packet_crossed")
    a.label("packet_crossed")
    a.ld_rr_nn("hl",PK_CROSS); a.inc_r("(hl)"); a.ld_a_hl(); a.cp_n(32); a.jp("packet_force_hit","nc")
    a.call("packet_read_cell"); a.cp_n(3); a.jp("packet_door_fallback","z")
    a.or_r("a"); a.jp("packet_hit","nz")
    a.ld_a_abs(PK_AXIS); a.or_r("a"); a.jp("packet_continue_y","nz")
    for name,next_distance,updates in (("x",PK_NX,((PK_EMIN,PK_MINY),(PK_EMAX,PK_MAXY))),
                                       ("y",PK_NY,((PK_EMIN,PK_MAXX),(PK_EMAX,PK_MINX)))):
        a.label("packet_continue_"+name)
        a.ld_rr_nn("hl",next_distance+1); a.inc_r("(hl)")
        for error,component in updates:
            for byte in range(1,4):
                if byte < 3: a.ld_a_abs(component+byte-1); a.ld_r_r("b","a")
                a.ld_a_abs(error+byte)
                if name == "x":
                    if byte == 1: a.add_a_r("b")
                    elif byte == 2: a.adc_a_r("b")
                    else: a.adc_a_n(0)
                else:
                    if byte == 1: a.sub_r("b")
                    elif byte == 2: a.sbc_a_r("b")
                    else: a.sbc_a_n(0)
                a.ld_abs_a(error+byte)
        a.jp("packet_bounds")

    a.label("packet_force_hit"); a.ld_r_n("a",1)
    a.label("packet_hit"); a.ld_abs_a(PK_MATERIAL)
    a.label("packet_project_ray")
    a.ld_a_abs(PK_FIRST); a.ld_abs_a(CAST_INDEX); a.ld_abs_a(Q14_RECORD); a.call(loader)
    for source,target in ((PK_X,DDA_MAP_X),(PK_Y,DDA_MAP_Y),(PK_AXIS,DDA_AXIS),
                          (PK_DISTANCE,DDA_DIST_L),(PK_DISTANCE+1,DDA_DIST_H),
                          (PK_MATERIAL,DDA_MATERIAL),(PK_CROSS,DDA_CROSSINGS)):
        a.ld_a_abs(source); a.ld_abs_a(target)
    a.ld_rr_nn("hl",ADAPTIVE_CASTS); a.inc_r("(hl)")
    a.call("cast_precision_done"); a.call("store_cast_result")
    a.call("packet_advance_ray"); a.jp("packet_project_ray","nz"); a.jp("packet_finished")

    a.label("packet_door_fallback")
    # No interval update has happened yet. Undo the one cell entry and let
    # every ray run the finite-panel code from the last certified cell.
    a.ld_rr_nn("hl",PK_CROSS); a.dec_r("(hl)")
    a.ld_a_abs(PK_AXIS); a.or_r("a"); a.jr("packet_undo_y","nz")
    a.ld_a_abs(PK_SX); a.ld_r_r("b","a"); a.ld_a_abs(PK_X); a.sub_r("b"); a.ld_abs_a(PK_X); a.jr("packet_scalar_all")
    a.label("packet_undo_y")
    a.ld_a_abs(PK_SY); a.ld_r_r("b","a"); a.ld_a_abs(PK_Y); a.sub_r("b"); a.ld_abs_a(PK_Y)
    a.label("packet_scalar_all")
    a.label("packet_fallback")
    a.label("packet_scalar_ray")
    a.ld_a_abs(PK_FIRST); a.ld_abs_a(CAST_INDEX); a.ld_abs_a(Q14_RECORD); a.call(loader)
    for source,target in ((PK_X,DDA_MAP_X),(PK_Y,DDA_MAP_Y),(PK_NX,DDA_NEXT_X_L),(PK_NX+1,DDA_NEXT_X_H),
                          (PK_NY,DDA_NEXT_Y_L),(PK_NY+1,DDA_NEXT_Y_H),(PK_CROSS,DDA_CROSSINGS)):
        a.ld_a_abs(source); a.ld_abs_a(target)
    a.ld_r_n("a",1); a.ld_abs_a(Q14_ACTIVE)
    a.ld_rr_nn("hl",ADAPTIVE_CASTS); a.inc_r("(hl)")
    a.ld_rr_nn("hl",Q14_FALLBACKS); a.inc_r("(hl)")
    if PACKET_BOUNDS_REUSE:
        a.call("packet_reused_bound"); a.or_r("a"); a.jr("packet_scalar_recompute","z")
        a.cp_n(1); a.ld_rr_nn("hl",PK_EMIN); a.jr("packet_scalar_error_ready","z")
        a.ld_rr_nn("hl",PK_EMAX)
        a.label("packet_scalar_error_ready")
        a.ld_rr_nn("de",Q14_ERROR); a.ld_rr_nn("bc",4); a.call("copy_bc")
        a.call("q14_loop"); a.jr("packet_scalar_project")
        a.label("packet_scalar_recompute"); a.call("q14_error_setup")
        a.label("packet_scalar_project")
    else:
        a.call("q14_error_setup")
    a.call("cast_precision_done"); a.call("store_cast_result")
    a.call("packet_advance_ray"); a.jp("packet_scalar_ray","nz"); a.jp("packet_finished")
    a.label("packet_generic_all")
    a.ld_a_abs(PK_FIRST); a.call("cast_and_store")
    a.call("packet_advance_ray"); a.jr("packet_generic_all","nz"); a.jp("packet_finished")

    a.label("packet_split")
    a.ld_a_abs(PK_STACK); a.cp_n(2); a.jp("packet_scalar_all","nc")
    a.ld_a_abs(PK_COUNT); a.cb("srl","a"); a.ld_abs_a(PK_COUNT)
    a.ld_a_abs(PK_STACK); a.or_r("a"); a.ld_rr_nn("de",PACKET_WORKSPACE+32); a.jr("packet_push_ready","z")
    a.ld_rr_nn("de",PACKET_WORKSPACE+64)
    a.label("packet_push_ready")
    a.push("de"); a.ld_rr_nn("hl",PACKET_WORKSPACE); a.ld_rr_nn("bc",32); a.call("copy_bc"); a.pop("hl")
    a.ld_a_abs(PK_COUNT); a.add_a_r("a"); a.ld_r_r("b","a"); a.ld_a_hl(); a.add_a_r("b"); a.ld_hl_a()
    if PACKET_BOUNDS_REUSE:
        a.ld_rr_nn("de",28); a.add_hl_rr("de"); a.ld_hl_n(2)
        a.ld_r_n("a",1); a.ld_abs_a(PK_MATERIAL)
    a.ld_rr_nn("hl",PK_STACK); a.inc_r("(hl)"); a.jp("packet_rebound")
    a.label("packet_finished")
    a.ld_a_abs(PK_STACK); a.or_r("a"); a.ret("z")
    a.cp_n(1); a.ld_rr_nn("hl",PACKET_WORKSPACE+32); a.jr("packet_pop_ready","z")
    a.ld_rr_nn("hl",PACKET_WORKSPACE+64)
    a.label("packet_pop_ready")
    a.ld_rr_nn("de",PACKET_WORKSPACE); a.ld_rr_nn("bc",32); a.call("copy_bc"); a.jp("packet_rebound")

    a.label("packet_advance_ray")
    a.ld_a_abs(PK_FIRST); a.add_a_n(2); a.ld_abs_a(PK_FIRST)
    a.ld_rr_nn("hl",PK_COUNT); a.dec_r("(hl)"); a.ret()
    a.label("packet_read_cell")
    a.ld_a_abs(PK_Y); a.cb("swap","a"); a.ld_r_r("b","a"); a.ld_a_abs(PK_X); a.add_a_r("b")
    a.ld_r_r("l","a"); a.ld_r_n("h",0xD0); a.ld_a_hl(); a.ret()
    if PACKET_BOUNDS_REUSE:
        a.label("packet_reused_bound")
        # Return zero for no inherited endpoint, 1 for Emin, 2 for Emax.
        a.ld_a_abs(PK_MATERIAL); a.or_r("a"); a.ret("z"); a.ld_r_r("c","a")
        a.ld_a_abs(PK_SX); a.ld_r_r("b","a"); a.ld_a_abs(PK_SY); a.cp_r("b")
        a.ld_r_r("a","c"); a.ret("z")
        a.xor_n(3); a.ret()
