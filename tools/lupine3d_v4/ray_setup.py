"""Cartridge-prepared coarse vectors and exact projection-table addresses."""
from .layout import *
from .resources import make_tables
from .precision import q14_direction
from .packets import packet_record


def ray_setup_record(angle: int, record: int) -> bytes:
    if record > 240:
        if ANCHOR_PACKETS and 241 <= record <= 250:
            return packet_record(angle,record-241)
        return bytes(RAY_SETUP_RECORD_BYTES)
    tables = make_tables()
    if record == 240:
        offset, correction = 0, 127
    else:
        index, prefix = (record, "ray") if record < 80 else (record-80, "physical")
        offset = int.from_bytes(tables[prefix+"_offsets"][index*2:index*2+2], "little", signed=True)
        correction = tables[prefix+"_corrections"][index]
    direction = ((angle << RAY_PLAYER_SHIFT)+offset) & (RAY_DIRECTION_COUNT-1)
    vector = tables["ray_packed"][direction*4:direction*4+4]
    data = bytearray(vector)+bytearray((direction & 255, direction >> 8, correction))
    for component in vector[:2]:
        slice_index = component*PROJECTION_LUT_CORRECTION_COUNT+correction-PROJECTION_LUT_CORRECTION_MIN
        if PROJECTION_STORAGE == "direct":
            data.extend((PROJECTION_LUT_BASE_BANK+slice_index//16, 0x40+(slice_index%16)*4))
        else:
            data.extend(slice_index.to_bytes(2,"little"))
    for component in q14_direction(angle,record):
        data.extend(abs(component).to_bytes(2,"little"))
    return bytes(data).ljust(RAY_SETUP_RECORD_BYTES,b"\0")


@lru_cache(maxsize=1)
def make_ray_setup_table() -> bytes:
    return b"".join(ray_setup_record(angle,record) for angle in range(256) for record in range(256))


def emit_ray_setup(a: Assembler):
    if CAMERA_SETUP:
        a.label("prepare_camera_setup")
        a.ld_a_abs(ANGLE); a.ld_r_r("b", "a"); a.cb("srl", "a"); a.cb("srl", "a")
        a.add_a_n(RAY_SETUP_ROM_BANK); a.ld_abs_a(FRAME_SETUP_BANK)
        a.ld_r_r("a", "b"); a.and_n(3); a.cb("swap", "a"); a.or_n(0x40); a.ld_abs_a(FRAME_SETUP_PAGE); a.ret()
    a.label("load_ray_setup")
    if CAMERA_SETUP:
        a.call("prepare_camera_setup")
        a.label("load_ray_setup_prepared")
    # Four aligned 4-KiB camera pages per bank, sixteen-byte ray records.
    if CAMERA_SETUP:
        a.ld_a_abs(FRAME_SETUP_BANK); a.ld_abs_a(0x2000)
    else:
        a.ld_a_abs(ANGLE); a.ld_r_r("b","a"); a.cb("srl","a"); a.cb("srl","a")
        a.add_a_n(RAY_SETUP_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_a_abs(Q14_RECORD); a.cb("swap","a"); a.ld_r_r("c","a"); a.and_n(0xF0); a.ld_r_r("l","a")
    a.ld_r_r("a","c"); a.and_n(15); a.ld_r_r("h","a")
    if CAMERA_SETUP:
        a.ld_a_abs(FRAME_SETUP_PAGE); a.or_r("h"); a.ld_r_r("h", "a")
    else:
        a.ld_r_r("a","b"); a.and_n(3); a.cb("swap","a"); a.or_r("h"); a.or_n(0x40); a.ld_r_r("h","a")
    for address in (DDA_ABS_X,DDA_ABS_Y,DDA_STEP_X,DDA_STEP_Y,DDA_ANGLE_L,DDA_ANGLE_H,DDA_CORRECTION,
                    RAY_PROJECTION_X,RAY_PROJECTION_X+1,RAY_PROJECTION_Y,RAY_PROJECTION_Y+1,
                    Q14_X,Q14_X+1,Q14_Y,Q14_Y+1):
        a.ldi_a_hl(); a.ld_abs_a(address)
    a.ld_r_n("a",1); a.ld_abs_a(0x2000); a.ld_abs_a(Q14_LOADED); a.ret()


def emit_prepared_projection(a: Assembler):
    a.ld_a_abs(Q14_RECORD); a.cp_n(241); a.jr("project_raw_address","nc")
    a.ld_rr_nn("hl",RAY_PROJECTION_X)
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("project_prepared_axis","z")
    a.inc_rr("hl"); a.inc_rr("hl")
    a.label("project_prepared_axis")
    if PROJECTION_STORAGE == "direct":
        a.ldi_a_hl(); a.ld_abs_a(0x2000); a.ld_a_hl(); a.ld_r_r("h","a")
        a.jp("project_read_depth")
    else:
        a.ldi_a_hl(); a.ld_r_r("e","a"); a.ld_a_hl(); a.ld_r_r("h","a"); a.ld_r_r("l","e")
        a.jp("project_paged_read")
    a.label("project_raw_address")
