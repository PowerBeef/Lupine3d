"""Deterministic 256-byte projection pages inside the original ROM allocation.

Directory banks contain 4096 three-byte records, leaving a declared 4096-byte
pad. Power-of-two indexing avoids runtime division, and no record straddles a
bank. Hybrid storage keeps the first page of each 1024-byte slice direct.
"""
from .layout import *
from .resources import make_projection_top_lut

DIRECTORY_RECORDS_PER_BANK = 4096
DIRECTORY_BANKS = 3
DIRECT_FIRST_BANKS = 36


@lru_cache(maxsize=3)
def pack_projection(mode):
    logical=make_projection_top_lut()
    if mode=="direct":
        return logical,dict(version=1,mode=mode,logical_bytes=len(logical),packed_bytes=len(logical),
                            directory_bytes=0,directory_padding_bytes=0,payload_bytes=len(logical),prepared_metadata="physical bank/high byte")
    if mode not in ("paged256","hybrid256"): raise ValueError(mode)
    pages=[logical[i:i+256] for i in range(0,len(logical),256)]
    first_pages=b"".join(pages[::4]) if mode=="hybrid256" else b""
    payload_start=DIRECTORY_BANKS*0x4000+len(first_pages)
    packed=bytearray(b"\xff"*payload_start);packed[DIRECTORY_BANKS*0x4000:]=first_pages
    seen={}; unique=0
    for i,page in enumerate(pages):
        if mode=="hybrid256" and i%4==0:
            physical=DIRECTORY_BANKS*0x4000+(i//4)*256
        else:
            if page not in seen:
                seen[page]=len(packed);packed.extend(page);unique+=1
            physical=seen[page]
        bank=PROJECTION_LUT_BASE_BANK+physical//0x4000;address=0x4000+physical%0x4000
        directory=(i//4096)*0x4000+(i%4096)*3
        assert directory%0x4000<=0x3FFD and address%256==0
        packed[directory:directory+3]=bytes((bank,address&255,address>>8))
    assert len(packed)<=len(logical)
    return bytes(packed),dict(version=2,mode=mode,logical_bytes=len(logical),packed_bytes=len(packed),
        directory_bytes=len(pages)*3,directory_allocated_bytes=DIRECTORY_BANKS*0x4000,
        directory_padding_bytes=DIRECTORY_BANKS*0x4000-len(pages)*3,
        direct_first_page_bytes=len(first_pages),unique_paged_payloads=unique,payload_bytes=len(packed)-DIRECTORY_BANKS*0x4000,
        directory_record_bytes=3,records_per_bank=4096,page_bytes=256,
        prepared_metadata="logical slice u16, little endian",unrelated_bank_assignments_preserved=True)


def read_packed(rom,logical_offset,mode):
    if not 0<=logical_offset<PROJECTION_LUT_BYTES: raise ValueError(logical_offset)
    if mode=="direct": return rom[PROJECTION_LUT_BASE_BANK*0x4000+logical_offset]
    page,offset=divmod(logical_offset,256)
    record=(PROJECTION_LUT_BASE_BANK+page//4096)*0x4000+(page%4096)*3
    bank,lo,hi=rom[record:record+3];address=lo|(hi<<8)
    return rom[bank*0x4000+address-0x4000+offset]


def emit_projection_storage(a: Assembler):
    if PROJECTION_STORAGE=="direct": return
    a.label("project_paged_read")  # HL=logical slice; D32_HIGH/LOW=0..511
    if PROJECTION_STORAGE=="hybrid256":
        a.ld_a_abs(D32_HIGH);a.or_r("a");a.jr("projection_directory","nz")
        a.ld_a_abs(D32_LOW);a.cb("bit","a",7);a.jr("projection_directory","nz")
        a.ld_r_r("a","l");a.and_n(63);a.or_n(0x40);a.ld_r_r("b","a")
        for _ in range(6):a.cb("srl","h");a.cb("rr","l")
        a.ld_r_r("a","l");a.add_a_n(PROJECTION_LUT_BASE_BANK+DIRECTORY_BANKS);a.ld_abs_a(0x2000)
        a.ld_r_r("h","b");a.jp("projection_payload_read")
        a.label("projection_directory")
    a.add_hl_rr("hl");a.add_hl_rr("hl")  # slice*4 + distance page
    a.ld_a_abs(D32_LOW);a.rlca();a.and_n(1);a.ld_r_r("b","a")
    a.ld_a_abs(D32_HIGH);a.add_a_r("a");a.or_r("b");a.or_r("l");a.ld_r_r("l","a")
    a.ld_r_r("a","h");a.cb("swap","a");a.and_n(15);a.add_a_n(PROJECTION_LUT_BASE_BANK);a.ld_abs_a(0x2000)
    a.ld_r_r("a","h");a.and_n(15);a.ld_r_r("h","a")
    a.ld_r_r("d","h");a.ld_r_r("e","l");a.add_hl_rr("hl");a.add_hl_rr("de")
    a.ld_r_r("a","h");a.or_n(0x40);a.ld_r_r("h","a")
    a.ldi_a_hl();a.ld_r_r("b","a");a.inc_rr("hl");a.ld_a_hl();a.ld_r_r("h","a")
    a.ld_r_r("a","b");a.ld_abs_a(0x2000)
    a.label("projection_payload_read")
    a.ld_a_abs(D32_LOW);a.add_a_r("a");a.ld_r_r("l","a")
    a.ldi_a_hl();a.ld_abs_a(TOP_RESULT);a.ld_a_hl();a.ld_abs_a(DEPTH_RESULT)
    a.ld_r_n("a",1);a.ld_abs_a(0x2000);a.jp("project_style_result")
