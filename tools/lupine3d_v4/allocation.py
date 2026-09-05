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


def memory_ledger(layout, code_end, resident_end, boot_bytes):
    l = layout
    A = Allocation
    rows = [
        A("ROM", 0, 0x8000, "resident engine/data and cartridge header"),
        A("ROM", l.PROJECTION_LUT_BASE_BANK * 0x4000, l.PRODUCT_LUT_BASE_BANK * 0x4000, "projection allocation"),
        A("ROM", l.PRODUCT_LUT_BASE_BANK * 0x4000, l.BANKED_ATLAS_ROM_BANK * 0x4000, "product table"),
        A("ROM", l.BANKED_ATLAS_ROM_BANK * 0x4000, (l.BANKED_ATLAS_ROM_BANK + 1) * 0x4000, "inactive atlas"),
        A("ROM", l.SEGMENT_TABLE_ROM_BANK * 0x4000, (l.SEGMENT_TABLE_ROM_BANK + 1) * 0x4000, "segment/surface records"),
        A("ROM", l.BOOT_ASSETS_ROM_BANK * 0x4000, l.BOOT_ASSETS_ROM_BANK * 0x4000 + boot_bytes, "boot art and authored state"),
        A("ROM", l.Q14_ROM_BANK * 0x4000, l.Q14_ROM_BANK * 0x4000 + l.Q14_ROM_BYTES, "Q14 directions"),
        A("ROM", l.RAY_SETUP_ROM_BANK * 0x4000, l.RAY_SETUP_ROM_BANK * 0x4000 + l.RAY_SETUP_ROM_BYTES, "prepared rays and packet padding"),
        A("ROM", 237 * 0x4000, 237 * 0x4000 + 7296, "unfolded diagnostic strips (reserved)"),
        A("WRAM0", 0xC000, 0xC600, "dynamic BG patterns", "composition through publication"),
        A("WRAM0", 0xC600, 0xC780, "BG map", "composition through publication"),
        A("WRAM0", 0xC780, 0xC790, "diagnostic strip scratch", "one strip lookup"),
        A("WRAM0", 0xC800, 0xC8BA, "OAM, publication and world epoch state"),
        A("WRAM0", 0xC8BA, 0xC8CE, "foreground queue and publication ownership"),
        A("WRAM0", 0xC8D0, 0xC8DE, "simulation/input clocks"),
        A("WRAM0", 0xC900, 0xCAC9, "snapshot copy / later fixture visibility", "exclusive sequential reuse"),
        A("WRAM0", 0xCB00, 0xCB6F, "saved render HRAM", "simulation service"),
        A("WRAM0", 0xCB70, 0xCB80, "dynamic cache key staging and pointer", "one tile lookup/composition"),
        A("WRAM0", 0xCB80, 0xCB9A, "atomic actor admission staging", "entity rendering, no yields"),
        A("WRAM0", 0xCC00, 0xCD00, "timestamped input queue"),
        A("WRAM0", 0xCD00, 0xCE00, "exact wall map key"),
        A("WRAM0", 0xCE00, 0xD000, "stack"),
        A("WRAM1", 0xD000, 0xD100, "snapshot map"),
        A("WRAM1", 0xD140, 0xD148, "snapshot camera"),
        A("WRAM1", 0xD200, 0xD2A0, "ray tops/styles"),
        A("WRAM1", 0xD2A0, 0xD300, "packet traversal workspace (reserved)", "packet traversal"),
        A("WRAM1", 0xD300, 0xD3A0, "ray keys/along"),
        A("WRAM1", 0xD3A0, 0xD3A4, "incremental certificate and prepared camera setup"),
        A("WRAM1", 0xD3A4, 0xD3AC, "physical refinement and coverage state"),
        A("WRAM1", 0xD3B0, 0xD3C4, "required physical-column coverage"),
        A("WRAM1", 0xD3C4, 0xD3D6, "Q8 actor transform scratch", "one uninterrupted projection"),
        A("WRAM1", 0xD3D6, 0xD3D8, "near-field perpendicular Q8 scratch", "one projection"),
        A("WRAM1", 0xD400, 0xD720, "physical descriptors and ray depth/segments"),
        A("WRAM1", 0xD720, 0xD7A0, "snapshot world and entity projection"),
        A("WRAM1", 0xD800, 0xD8A0, "physical segments"),
        A("WRAM1", 0xD8A0, 0xD8C8, "Q14 and door/LOS scratch"),
        A("WRAM1", 0xD8D0, 0xD8DA, "mask submission scratch"),
        A("WRAM1", 0xD8E0, 0xD8E5, "LOD history"),
        A("WRAM1", 0xD8F0, 0xD8F7, "surface and prepared projection metadata"),
        A("WRAM1", 0xD900, 0xDA00, "scanlines, actor slots, decor and HUD"),
        A("WRAM1", 0xDA00, 0xDC00, "masked OBJ patterns"),
        A("WRAM1", 0xDC00, 0xDD80, "BG attributes"),
        A("WRAM1", 0xDE00, 0xDE50, "ray surface profiles"),
        A("WRAM1", 0xDE80, 0xDF20, "physical surface profiles"),
        A("WRAM1", 0xDF20, 0xDF42, "wall cache metadata"),
        A("WRAM1", 0xDF42, 0xDF56, "physical validity bits (reserved)"),
        A("WRAM1", 0xDF60, 0xE000, "physical depth (reserved)"),
        A("WRAM2", 0xD000, 0xE000, "live world and query scratch"),
        A("WRAM3", 0xD000, 0xE000, "128 x 32-byte dynamic cache (reserved)"),
        A("WRAM4", 0xD000, 0xD0A0, "foreground composite DMA buffer"),
        A("WRAM4", 0xD100, 0xD1A0, "authoritative published world OAM"),
        A("WRAM4", 0xD200, 0xD2A0, "sixteen ten-byte foreground event slots"),
        A("HRAM", 0xFF80, 0xFF80 + l.HRAM_BYTES_USED, "hot render / ISR state"),
        A("HRAM", 0xFFF4, 0xFFFE, "OAM DMA code"),
        A("OAM", 0, 40, "ten UI, sixteen world, fourteen unused objects"),
    ]
    for bank in (0, 1):
        rows.extend((A(f"VRAM{bank}", 0x8000, 0x8800, "OBJ-only patterns / bank-0 HUD"),
                     A(f"VRAM{bank}", 0x8800, 0x9800, "BG patterns"),
                     A(f"VRAM{bank}", 0x9800, 0xA000, "BG maps / attributes")))
    validate_allocations(rows)
    assert code_end < 0x4000, "bank-switching code exceeded fixed ROM"
    assert 0x8000 - resident_end >= 3000, "resident reserve below 3,000 bytes"
    # Copy spans are shared with the emitter; new render-only allocations must
    # never enter the live-world copy in either direction.
    reserved = [(0xD2A0, 0xD300), (0xD3A0, 0xD3D8), (0xDF42, 0xDF56), (0xDF60, 0xE000)]
    for start, count in l.WORLD_COPY_RANGES:
        for low, high in reserved:
            assert start + count <= low or high <= start
    assert sum(count for _, count in l.WORLD_COPY_RANGES) == 457
    assert l.WORLD_COPY_BUFFER + 457 <= l.RENDER_HRAM_SAVE
    return dict(schema="lupine3d.allocations.v1", ranges=[asdict(r) for r in rows],
                free_wram_banks=[5, 6, 7], fixed_code_free_bytes=0x4000-code_end,
                resident_free_bytes=0x8000-resident_end,
                snapshot_copy_ranges=list(l.WORLD_COPY_RANGES),
                packet_records_per_yaw=[241, 251], prepared_record_bytes=16)
