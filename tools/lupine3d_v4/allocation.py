"""Machine-checked allocation ledger. Ranges use inclusive start/exclusive end."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Allocation:
    space: str
    start: int
    end: int
    owner: str
    lifetime: str = "persistent"


def validate_allocations(rows):
    for row in rows:
        assert row.start < row.end, row
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            assert a.space != b.space or a.end <= b.start or b.end <= a.start, (a, b)


def memory_ledger(layout, code_end, resident_end, boot_bytes, raw_ray_bytes=0):
    l = layout
    A = Allocation
    rows = [
        A("ROM", 0, 0x8000, "resident engine/data and cartridge header"),
        A("ROM", l.PROJECTION_LUT_BASE_BANK * 0x4000, l.PRODUCT_LUT_BASE_BANK * 0x4000, "projection allocation"),
        A("ROM", l.PRODUCT_LUT_BASE_BANK * 0x4000, l.BANKED_ATLAS_ROM_BANK * 0x4000, "product table"),
        A("ROM", l.BANKED_ATLAS_ROM_BANK * 0x4000, (l.BANKED_ATLAS_ROM_BANK + 1) * 0x4000, "inactive atlas"),
        *([] if l.SEGMENT_TABLE_ROM_BANK in (l.TEXTURE_WINDOW_BANKS if l.TEXTURED_WALLS else ()) else
          [A("ROM", l.SEGMENT_TABLE_ROM_BANK * 0x4000, (l.SEGMENT_TABLE_ROM_BANK + 1) * 0x4000,
             "reserved (levels now carry their own segment/surface records)")]),
        A("ROM", l.BOOT_ASSETS_ROM_BANK * 0x4000, l.BOOT_ASSETS_ROM_BANK * 0x4000 + boot_bytes, "boot art and authored state"),
        A("ROM", l.WEAPON_ROM_BANK * 0x4000, l.WEAPON_ROM_BANK * 0x4000 + l.WEAPON_COUNT * l.WEAPON_TILE_BYTES,
          "weapon cel sheets, streamed into the OBJ window one at a time"),
        A("ROM", l.Q14_ROM_BANK * 0x4000, l.Q14_ROM_BANK * 0x4000 + l.Q14_ROM_BYTES, "Q14 directions"),
        A("ROM", l.RAY_SETUP_ROM_BANK * 0x4000, l.RAY_SETUP_ROM_BANK * 0x4000 + l.RAY_SETUP_ROM_BYTES, "prepared rays and packet padding"),
        A("ROM", 237 * 0x4000, 237 * 0x4000 + l.MICRO_STATE_COUNT*384, "unfolded diagnostic strips (reserved)"),
        A("ROM", l.RAW_RAY_ROM_BANK * 0x4000, l.RAW_RAY_ROM_BANK * 0x4000 + raw_ray_bytes, "cold raw vectors and camera-plane tables"),
        A("ROM", l.MUSIC_ROM_BANK * 0x4000, (l.MUSIC_ROM_BANK + 1) * 0x4000, "songs and note periods"),
        A("ROM", l.LEVEL_ROM_BANK_BASE * 0x4000,
          l.level_rom_offset(l.LEVEL_COUNT - 1) + l.LEVEL_PAYLOAD_END - 0x4000,
          f"campaign levels, {l.LEVELS_PER_BANK} per bank in {l.LEVEL_SLOT_PITCH}-byte slots"),
        A("WRAM0", 0xC000, 0xC600, "dynamic BG patterns", "composition through publication"),
        A("WRAM0", 0xC600, 0xC600 + l.VIEW_MAP_BYTES,
          "BG map / screen digits and code entry while a full-screen mode is up",
          "exclusive sequential reuse"),
        A("WRAM0", l.STRIP_SCRATCH, l.STRIP_SCRATCH + 16, "diagnostic strip scratch", "one strip lookup"),
        A("WRAM0", l.MUSIC_STATE, l.MUSIC_STATE_END, "music sequencer state"),
        A("WRAM0", l.MUSIC_STATE_END, l.WORLD_STATE_END, "skill and per-actor stat scratch"),
        A("WRAM0", l.WORLD_STATE_END, l.CAMPAIGN_SCALARS_END,
          "campaign scalars: actor count, palette set, weapons owned, level page, texture directory"),
        A("WRAM0", l.LIVE_MAP_GEN, l.MAP_GENERATION_END, "live and snapshot map generations"),
        A("WRAM0", l.TAIL_PENDING, l.TAIL_PENDING_END, "overlapped publication hand-off"),
        A("WRAM0", 0xC800, 0xC8BA, "OAM, publication and world epoch state"),
        A("WRAM0", 0xC8BA, 0xC8CE, "foreground queue and publication ownership"),
        A("WRAM0", l.DYN_STREAMED, l.DYN_STREAMED + 1, "dynamic patterns already streamed by HBlank DMA", "composition through publication"),
        A("WRAM0", 0xC8CF, 0xC8D0, "presentation mode"),
        A("WRAM0", 0xC8D0, 0xC8DE, "simulation/input clocks"),
        A("WRAM0", 0xC8F0, 0xC900, "screen composition and level selection"),
        A("WRAM0", l.WORLD_COPY_BUFFER, l.WORLD_COPY_BUFFER + l.WORLD_COPY_BYTES,
          "snapshot copy / later fixture visibility", "exclusive sequential reuse"),
        A("WRAM0", l.COLUMN_ROWS, l.COLUMN_ROWS + l.FOLDED_ROWS, "folded column tile IDs", "one composed column"),
        A("WRAM0", 0xCB00, 0xCB6F, "saved render HRAM", "simulation service"),
        A("WRAM0", 0xCB70, 0xCB80, "dynamic cache key staging and pointer", "one tile lookup/composition"),
        A("WRAM0", 0xCB80, 0xCB9A, "atomic actor admission staging", "entity rendering, no yields"),
        A("WRAM0", 0xCC00, 0xCD00, "timestamped input queue"),
        A("WRAM0", 0xCD00, 0xCE00, "exact wall map key"),
        A("WRAM0", 0xCE00, 0xD000, "stack"),
        A("WRAM1", 0xD000, 0xD100, "snapshot map"),
        A("WRAM1", 0xD140, 0xD148, "snapshot camera"),
        A("WRAM1", 0xD200, 0xD2A0, "ray tops/styles"),
        A("WRAM1", 0xD2A0, 0xD300, "packet traversal workspace (reserved)", "packet traversal") if not l.TEXTURED_WALLS
        else A("WRAM1", l.RAY_U, l.RAY_U + 80, "ray texture coordinates (anchor packets excluded)"),
        A("WRAM1", 0xD300, 0xD3A0, "ray keys/along"),
        A("WRAM1", 0xD3A0, 0xD3A4, "incremental certificate and prepared camera setup"),
        A("WRAM1", 0xD3A4, 0xD3AC, "physical refinement and coverage state"),
        A("WRAM1", 0xD3B0, 0xD3C4, "required physical-column coverage"),
        A("WRAM1", 0xD3C4, 0xD3D6, "Q8 actor transform scratch", "one uninterrupted projection"),
        A("WRAM1", 0xD3D6, 0xD3D8, "near-field perpendicular Q8 scratch", "one projection"),
        A("WRAM1", 0xD3D8, 0xD400, "compact HUD packet and animation scratch"),
        A("WRAM1", 0xD400, 0xD720, "physical descriptors and ray depth/segments"),
        A("WRAM1", l.VRAM_PROFILE, l.VRAM_PROFILE + l.WORLD_WINDOW_BYTES, "snapshot world, entity projection and campaign state"),
        A("WRAM1", l.ACTOR_PROJECTION, l.ACTOR_PROJECTED + l.MAX_ACTORS, "per-slot actor projection records", "entity rendering"),
        A("WRAM1", 0xD800, 0xD8A0, "physical segments"),
        A("WRAM1", 0xD8A0, 0xD8C8, "Q14 and door/LOS scratch"),
        A("WRAM1", 0xD8D0, 0xD8DA, "mask submission scratch"),
        A("WRAM1", l.LOD_HISTORY, l.LOD_HISTORY + l.MAX_ACTORS + 1, "LOD history"),
        A("WRAM1", 0xD8F0, 0xD8F7, "surface and prepared projection metadata"),
        A("WRAM1", 0xD900, 0xDA00, "scanlines, actor slots, decor and HUD"),
        A("WRAM1", 0xDA00, 0xDC00, "masked OBJ patterns"),
        A("WRAM1", 0xDC00, 0xDC00 + l.VIEW_MAP_BYTES, "BG attributes"),
        A("WRAM1", 0xDE00, 0xDE50, "ray surface profiles"),
        A("WRAM1", 0xDE80, 0xDF20, "physical surface profiles"),
        A("WRAM1", l.WALL_CACHE_META, l.WALL_CACHE_META + l.WALL_KEY_META_BYTES, "wall cache metadata"),
        A("WRAM1", l.DECAL_RECORD, l.DECAL_END, "wall fixture projection scratch", "entity rendering"),
        A("WRAM1", 0xDF42, 0xDF56, "physical validity bits (reserved)"),
        A("WRAM1", 0xDF60, 0xE000, "physical depth (reserved)" if not l.TEXTURED_WALLS
          else "physical-pixel texture coordinates (physical depth excluded)"),
        *([A("WRAM1", l.U_RESULT, l.U_SLOPE_H + 1, "along-face result and slope scratch", "one cast"),
           A("WRAM0", l.TEX_RUNS, l.TEX_RUNS + 8 * l.TEX_RUN_BYTES, "textured run records", "one composed column"),
           A("WRAM0", l.DYN_INFLIGHT, l.DYN_INFLIGHT + 1, "first pattern of the HBlank transfer in flight", "composition through publication"),
           A("WRAM1", l.TEX_MASKS, l.TEX_MASKS + 8, "boundary tile outline masks", "one composed tile"),
           A("WRAM1", l.TEX_WINDOWS, l.TEX_WINDOWS + 8 * 16, "run row-window caches", "one composed column"),
           A("ROM", l.TEXTURE_LUT_ROM_BANK * 0x4000, (l.TEXTURE_LUT_ROM_BANK + 1) * 0x4000,
             "texture slopes, height-class rows and stride classes"),
           *(A("ROM", bank * 0x4000, (bank + 1) * 0x4000, "texture row windows (three blocks per bank)")
             for bank in l.TEXTURE_WINDOW_BANKS)] if l.TEXTURED_WALLS else []),
        A("WRAM2", 0xD000, 0xE000, "live world and query scratch"),
        A("WRAM3", 0xD000, 0xE000, "128 x 32-byte dynamic cache (reserved)"),
        A("WRAM4", 0xD000, 0xD0A0, "foreground composite DMA buffer"),
        A("WRAM4", 0xD100, 0xD1A0, "authoritative published world OAM"),
        A("WRAM4", 0xD200, 0xD2A0, "sixteen ten-byte foreground event slots"),
        A("WRAM5", l.MUSIC_NOTE_TABLE, l.MUSIC_NOTE_TABLE + 128, "sequencer note periods"),
        A("WRAM5", l.MUSIC_ROWS, 0xE000, "copied song rows", "one song"),
        A("HRAM", 0xFF80, 0xFF80 + l.HRAM_BYTES_USED, "hot render / ISR state"),
        A("HRAM", 0xFFF4, 0xFFFE, "OAM DMA code"),
        A("OAM", 0, 40, "ten UI, sixteen world, fourteen unused objects"),
    ]
    for bank in (0, 1):
        rows.extend((A(f"VRAM{bank}", 0x8000, 0x8800, "OBJ-only patterns / bank-0 HUD"),
                     A(f"VRAM{bank}", 0x8800, 0x9800, "BG patterns"),
                     A(f"VRAM{bank}", 0x9800, 0xA000, "BG maps / attributes")))
    validate_allocations(rows)
    # The real MBC5 rule is checked against the emitted image in
    # bank_safety.py. This is the budget behind it: the resident sections -
    # every routine that writes the bank register, can run inside another
    # section's bank window, or is reachable from an interrupt vector - are
    # emitted before the data and so must all fit under the boundary.
    assert code_end < 0x4000, f"the fixed half no longer holds the resident sections (end {code_end:#06x})"
    assert 0x8000 - resident_end >= 3000, "resident reserve below 3,000 bytes"
    # Copy spans are shared with the emitter; new render-only allocations must
    # never enter the live-world copy in either direction.
    reserved = [(0xD2A0, 0xD300), (0xD3A0, 0xD3D8), (0xDF42, 0xDF56), (0xDF60, 0xE000)]
    for start, count in l.WORLD_COPY_RANGES:
        for low, high in reserved:
            assert start + count <= low or high <= start
    assert l.EXIT_CELL_Y < l.SHOT_TICK < l.ART_STATE_END <= l.VRAM_PROFILE + l.WORLD_WINDOW_BYTES
    # Campaign state rides the copy that is already made; it never grows it.
    assert l.ART_STATE_END == l.GAME_STATE and l.GAME_STATE_END <= l.VRAM_PROFILE + l.WORLD_WINDOW_BYTES
    assert l.HUD_PACKET + l.HUD_PACKET_BYTES <= 0xD400
    assert l.WEAPON_TILE_BASE >= 32
    assert l.RETICLE_TILE + (6 if l.SABLE_ART else 4) <= 128
    assert l.SENTINEL_MID_TILE_BASE + l.SENTINEL_MID_FRAMES*l.SENTINEL_MID_TILES_PER_FRAME + 64 <= 256
    # The copy is a contract: the map, the camera, the world window and every
    # actor slot, and nothing else. A change here changes what the renderer
    # can see of the simulation.
    assert l.WORLD_COPY_BYTES == 256 + 8 + l.WORLD_WINDOW_BYTES + l.MAX_ACTORS * 16
    assert l.WORLD_COPY_BUFFER + l.WORLD_COPY_BYTES <= l.COLUMN_ROWS
    assert l.COLUMN_ROWS + l.FOLDED_ROWS <= l.RENDER_HRAM_SAVE
    # The sequencer state sits above the BG map in every display profile and
    # never overlaps the diagnostic strip scratch. Screen state borrows the
    # bottom of the map buffer, which composition refills on every enter_world,
    # so it has to fit inside the buffer and clear of that scratch.
    assert 0xC600 + l.VIEW_MAP_BYTES <= l.MUSIC_STATE
    assert l.SCREEN_STATE == 0xC600 and l.SCREEN_STATE_END <= 0xC600 + l.VIEW_MAP_BYTES
    assert l.SCREEN_STATE_END <= l.STRIP_SCRATCH or l.STRIP_SCRATCH + 16 <= 0xC600
    return dict(schema="lupine3d.allocations.v1", ranges=[asdict(r) for r in rows],
                free_wram_banks=[6, 7], fixed_code_free_bytes=0x4000-code_end,
                resident_free_bytes=0x8000-resident_end,
                snapshot_copy_ranges=list(l.WORLD_COPY_RANGES),
                packet_records_per_yaw=[241, 251], prepared_record_bytes=16)
