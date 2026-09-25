"""Original Sable Outpost pixel art, authored directly in native 2bpp pixels."""
from functools import lru_cache
from .layout import *

from .fonts import FONT, HUD_FONT  # noqa: E402,F401  (the engine's fonts)

def canvas(w, h, colour=0): return [[colour] * w for _ in range(h)]

def rect(px, x, y, w, h, colour):
    for yy in range(max(0, y), min(len(px), y + h)):
        for xx in range(max(0, x), min(len(px[0]), x + w)): px[yy][xx] = colour

def text_pixels(px, text, x, y, colour=2, scale=1):
    for character in text:
        glyph = FONT.get(character, "0" * 15)
        for i, bit in enumerate(glyph):
            if bit == "1": rect(px, x + (i % 3) * scale, y + (i // 3) * scale, scale, scale, colour)
        x += 4 * scale

def tiles(px):
    return b"".join(tile_from_pixels([r[x:x+8] for r in px[y:y+8]])
                    for y in range(0, len(px), 8) for x in range(0, len(px[0]), 8))

def pairs(px):
    data = tiles(px); width = len(px[0]) // 8
    return b"".join(data[(row * width + col) * 16:(row * width + col + 1) * 16]
                    for pair in range(len(px)//16) for col in range(width)
                    for row in (pair * 2, pair * 2 + 1))

def make_weapon_tiles():
    px = canvas(32, 32)
    # Long foreshortened barrel, front sight, receiver and offset pump.
    rect(px, 15, 1, 2, 3, 3)
    for y in range(4, 24):
        half = 3 + (y - 4) // 5
        rect(px, 16-half, y, half*2, 1, 1)
        rect(px, 17-half, y, half*2-2, 1, 2)
        px[y][16-half+1] = 3
    rect(px, 13, 5, 6, 4, 1); rect(px, 14, 6, 4, 1, 0)
    rect(px, 18, 10, 2, 7, 1)
    for y in (13, 16, 19): rect(px, 13, y, 5, 1, 1)
    for y in range(21, 32):
        half = 7 + (y-21)//4
        rect(px, 16-half, y, half*2, 1, 1)
        rect(px, 17-half, y, half*2-2, 1, 2)
        rect(px, 14, y, 3, 1, 3)
    rect(px, 19, 23, 3, 5, 1); px[23][19] = 3
    # Gloved support hands use separate OBJ palettes at the outside edges.
    for y in range(23, 32):
        rect(px, max(0, 6-(y-23)), y, 8, 1, 1)
        rect(px, max(1, 7-(y-23)), y, 6, 1, 2)
        rect(px, 25, y, min(7, 2+(y-23)), 1, 1)
        rect(px, 26, y, min(5, 1+(y-23)), 1, 2)
    for y in (26, 29): rect(px, 3, y, 4, 1, 3); rect(px, 27, y, 3, 1, 3)
    return pairs(px)

def _sentinel_near_frame(frame):
    px = canvas(16, 32); bob = frame & 1; attack = frame == 2
    # Armoured respirator, recessed eye slit and a broad asymmetric silhouette.
    rect(px, 5, 2+bob, 7, 8, 1); rect(px, 6, 2+bob, 5, 3, 2)
    rect(px, 6, 5+bob, 5, 2, 3); rect(px, 7, 5+bob, 3, 1, 1)
    rect(px, 7, 8+bob, 3, 2, 2)
    for x in (5, 11): rect(px, x, 7+bob, 1, 2, 3)
    rect(px, 2, 10+bob, 12, 5, 1); rect(px, 3, 10+bob, 4, 3, 2)
    rect(px, 10, 10+bob, 3, 3, 2); px[10+bob][3] = 3
    rect(px, 4, 14+bob, 9, 9, 1); rect(px, 5, 14+bob, 6, 7, 2)
    rect(px, 6, 14+bob, 2, 3, 3); rect(px, 8, 18+bob, 3, 2, 1)
    rect(px, 2, 15+bob, 3, 8, 1); rect(px, 2, 16+bob, 2, 4, 2)
    rect(px, 12, 14 if attack else 16+bob, 3, 8, 1)
    rect(px, 13, 15 if attack else 17+bob, 1, 4, 3)
    rect(px, 5, 22+bob, 7, 2, 3)
    for left, shift in ((4, bob), (10, 1-bob)):
        rect(px, left, 24, 3, 6-shift, 2); rect(px, left-1, 29-shift, 4, 2, 1)
        rect(px, left, 27-shift, 2, 1, 3)
    if attack: rect(px, 14, 13, 2, 2, 3)
    if frame == 3:
        for y in range(2, 28):
            for x in range(16):
                if px[y][x] == 2 and (x+y)%3 == 0: px[y][x] = 3
    return tiles(px)

def _sentinel_far_frame(frame):
    px = canvas(8, 16); b = frame & 1
    rect(px, 2, 1+b, 4, 5, 1); rect(px, 3, 1+b, 2, 2, 2)
    rect(px, 3, 3+b, 2, 1, 3); rect(px, 1, 6+b, 6, 6, 1)
    rect(px, 2, 6+b, 4, 5, 2); rect(px, 3, 7+b, 1, 2, 3)
    rect(px, 2, 12, 2, 4-b, 2); rect(px, 5, 12, 2, 3+b, 1)
    return tiles(px)

def make_obj_ui_tiles():
    reticle = canvas(8, 16)
    for x,y in ((1,3),(2,3),(5,3),(6,3),(3,1),(3,2),(3,5),(3,6)):
        reticle[y][x] = 3
    flash = canvas(8,16)
    for y in range(8):
        for x in range(8):
            d = abs(x-3)+abs(y-3)
            if d < 5 and (d < 3 or (x+y)%2): flash[y][x] = 3 if d<2 else 2
    return tiles(reticle) + tiles(flash)

def make_fixture_tiles():
    """The game's wall fixture sheet (game.json `sprites.fixtures`): per
    family, 16x16 cels drawn at the three distances (16, 8 and 4 pixels
    across, top-left), then a half-width copy of the near cel."""
    from .sprite_assets import frames
    cels = frames(GAME.sprites['fixtures'])
    assert len(cels) == 3 * len(GAME.fixture_kinds) and len(cels[0]) == len(cels[0][0]) == 16
    out = bytearray()
    for kind in range(len(GAME.fixture_kinds)):
        near, middle, far = ([list(row) for row in cels[kind * 3 + n]] for n in range(3))
        out.extend(pairs(near))
        out.extend(pairs([row[:8] for row in middle]))
        out.extend(pairs([row[:8] for row in far]))
        out.extend(pairs([[row[x*2] for x in range(8)] for row in near]))
        out.extend(bytes(6*16))  # sixteen source patterns per fixture family
    return bytes(out)

@lru_cache(maxsize=1)
def hud_assets():
    if COMPACT_DISPLAY: return compact_hud_assets()
    # Unsigned tiles 32..127 in bank 0: disjoint from both masked OBJ pages.
    payload = []
    for digit in "0123456789":
        px = canvas(8,16,0); text_pixels(px,digit,1,2,2,2)
        payload.extend(tiles(px)[i:i+16] for i in (0,16))
    screen = canvas(160,48,0)
    rect(screen,0,0,160,1,3); rect(screen,0,1,160,1,1)
    for x,w in ((4,43),(54,52),(113,43)):
        rect(screen,x,8,w,29,1); rect(screen,x,8,w,1,3)
        rect(screen,x,9,1,27,3); rect(screen,x+w-1,9,1,27,0)
    text_pixels(screen,"HEALTH",8,10,2); text_pixels(screen,"LUPINE",68,2,2)
    text_pixels(screen,"STATUS",68,10,2); text_pixels(screen,"HOSTILE",120,10,2)
    text_pixels(screen,"A FIRE  B USE",8,40,2)
    text_pixels(screen,"EXIT",104,40,3)
    # Compact wolf helmet portrait; cyan visor, layered steel and chin guard.
    face = canvas(16,16,0)
    for y in range(1,15):
        inset = max(0,3-y, y-11)
        rect(face,2+inset,y,12-2*inset,1,3)
        rect(face,3+inset,y,10-2*inset,1,1)
    rect(face,3,5,10,4,2); rect(face,4,6,8,1,0)
    rect(face,6,10,4,3,3); rect(face,7,10,2,2,0)
    for y in range(16): screen[16+y][72:88] = face[y]
    # Dynamic digit slots are deliberately blank in the static dictionary.
    for x in (16,24,128,136): rect(screen,x,16,8,16,0)
    tilemap = bytearray([32] * 1024); attrs = bytearray([1] * 1024)
    for y in range(6):
        for x in range(20):
            pattern = tile_from_pixels([row[x*8:x*8+8] for row in screen[y*8:y*8+8]])
            if pattern not in payload: payload.append(pattern)
            tilemap[(12+y)*32+x] = 32+payload.index(pattern)
    statuses = {}
    for label in ("LOCK","OPEN","DEAD","DONE"):
        px = canvas(24,8,0); text_pixels(px,label,0,0,2)
        ids=[]
        for i in range(3):
            pattern=tiles(px)[i*16:(i+1)*16]
            if pattern not in payload: payload.append(pattern)
            ids.append(32+payload.index(pattern))
        statuses[label] = ids
    assert len(payload) <= 96, f"HUD needs {len(payload)} of 96 tiles"
    return b"".join(payload), bytes(tilemap), bytes(attrs), statuses




def hud_text(px, text, x, y, colour=2):
    for character in text:
        for yy, row in enumerate(HUD_FONT[character]):
            for xx, bit in enumerate(row):
                if bit == '1': rect(px, x+xx, y+yy, 1, 1, colour)
        x += 6


def compact_hud_assets():
    """Instrument strip; dynamic tiles preserve the divider when touching row zero."""
    from .sprite_assets import frames
    from .steel_hud import HEALTH_FONT, paint
    # The game's HUD and portrait sheets; the historical compact profile keeps
    # the showcase's compact HUD.
    screen=frames(GAME.sprites['hud'] if SLIM_DISPLAY else 'hud')[0]
    def background(x,y,w,h):
        return [list(row[x:x+w]) for row in screen[y:y+h]]
    payload=[]
    def intern(pattern):
        if pattern not in payload:payload.append(pattern)
        return 32+payload.index(pattern)
    def intern_pair(top,bottom):
        # The publisher derives the lower tile as top+1, keeping the existing
        # packet size when the lowered text crosses into the third HUD row.
        for i in range(len(payload)-1):
            if payload[i]==top and payload[i+1]==bottom:return 32+i
        index=len(payload);payload.extend((top,bottom));return 32+index
    # Preserve the public twenty digit IDs, even when glyphs share a tile.
    for digit in '0123456789':
        if SLIM_DISPLAY:
            px=background(24,0,8,16);paint(px,HEALTH_FONT[digit],1,6,ink=2)
        else:
            px=canvas(8,16);text_pixels(px,digit,1,2,2,2)
        payload.extend(tiles(px)[i:i+16] for i in (0,16))
    for digit in '0123456789':
        px=background(112,8,8,8) if SLIM_DISPLAY else canvas(8,8)
        hud_text(px,digit,1,1 if SLIM_DISPLAY else 0)
        payload.append(tile_from_pixels(px))
    tilemap=bytearray([32]*1024);attrs=bytes([1]*1024)
    for y in range(HUD_HEIGHT//8):
        for x in range(20):
            tilemap[(VIEW_ROWS+y)*32+x]=intern(tile_from_pixels([row[x*8:x*8+8] for row in screen[y*8:y*8+8]]))
    statuses={}
    for label in ('LOCK','OPEN','DEAD','DONE'):
        # Preserve the runtime record keys/packet ABI. The slim panel states
        # the next objective, rather than suggesting a physical door position.
        # The words are the game's (game.json `hud.words`).
        words=GAME.hud_words
        text={'LOCK':words['hunt'],'OPEN':words['exit'],'DEAD':words['dead'],'DONE':words['done']}[label] if SLIM_DISPLAY else label
        if SLIM_DISPLAY:
            px=background(128,0,24,24)
            hud_text(px,text,0,10,2)
            if label in ('LOCK','OPEN'):text_pixels(px,words['caption'],0,4,1)
            data=tiles(px)
            statuses[label]=[intern_pair(data[(3+i)*16:(4+i)*16],data[(6+i)*16:(7+i)*16]) for i in range(3)]
            statuses['caption_'+label]=[intern(data[i*16:(i+1)*16]) for i in range(2)]
        else:
            px=canvas(24,8);hud_text(px,text,0,0,2)
            statuses[label]=[intern(tiles(px)[i*16:(i+1)*16]) for i in range(3)]
            prefix=canvas(16,8)
            if label in ('LOCK','OPEN'):text_pixels(prefix,'EXIT',0,2,3)
            statuses['caption_'+label]=[intern(tiles(prefix)[i*16:(i+1)*16]) for i in range(2)]
    from .sprite_assets import frames
    for index,px in enumerate(frames(GAME.sprites['portrait'] if SLIM_DISPLAY else 'helmet')):
        # Palette mapping: source steel becomes HUD steel, ivory stays readable.
        if SLIM_DISPLAY:
            mapped=background(72,0,16,24)
            for y,row in enumerate(px):mapped[y+4]=list(row)
        else:
            mapped=[[{0:0,1:1,2:3,3:2}[c] for c in row] for row in px]
        statuses['portrait'+str(index)]=[intern(tiles(mapped)[i*16:(i+1)*16]) for i in range(HUD_PORTRAIT_TILES)]
    assert len(payload)<=96,f'compact HUD needs {len(payload)} / 96 tiles'
    return b''.join(payload),bytes(tilemap),attrs,statuses


_legacy_weapon_tiles=make_weapon_tiles
_legacy_near_frame=_sentinel_near_frame
_legacy_far_frame=_sentinel_far_frame
_legacy_obj_ui_tiles=make_obj_ui_tiles

def make_weapon_tiles():
    if not SABLE_ART:return _legacy_weapon_tiles()
    from .sprite_assets import compile_sheet
    return compile_sheet(GAME.weapons[0].sprite,paired=True)

def _sentinel_near_frame(frame):
    if not SABLE_ART:return _legacy_near_frame(frame)
    from .sprite_assets import compile_frame
    return compile_frame(GAME.sprites['actor_near'],frame)

def _sentinel_far_frame(frame):
    if not SABLE_ART:return _legacy_far_frame(frame)
    from .sprite_assets import compile_frame
    return compile_frame(GAME.sprites['actor_far'],frame)

def make_obj_ui_tiles():
    if not SABLE_ART:return _legacy_obj_ui_tiles()
    from .sprite_assets import compile_sheet
    tiles_out = compile_sheet(GAME.sprites['reticle'])+compile_sheet(GAME.sprites['muzzle_flash'])
    if KEY_HUD:
        # A key four pixels wide, a bow over a toothed shaft, over an empty
        # pattern: each colour's object shows it in its own half of the cell.
        key = canvas(8, 16)
        for y, row in enumerate((".33.", "3..3", "3..3", ".33.", ".3..", ".33.", ".3..", ".33.")):
            for x, pixel in enumerate(row):
                key[y][x] = 3 if pixel == "3" else 0
        tiles_out += tiles(key)
    return tiles_out


def compact_hud_pixels(height=32):
    main_shift = 2 if height == 24 else 0
    screen=canvas(160,height);rect(screen,0,0,160,1,1)
    # A cross and a tiny hostile helmet replace permanent headings.
    rect(screen,9,12-main_shift,2,8,2);rect(screen,6,15-main_shift,8,2,2)
    # The hostile icon occupies its own tile, with a full blank tile before
    # the small count. Its silhouette cannot be overwritten by digit updates.
    rect(screen,105,9-main_shift,6,5,3);rect(screen,104,11-main_shift,8,3,3)
    rect(screen,106,10-main_shift,4,1,2);rect(screen,106,12-main_shift,4,1,0)
    rect(screen,107,14-main_shift,2,1,3)
    text_pixels(screen,'EXIT',128 if height==24 else 104,3 if height==24 else 18,3)
    return screen
