Current development defaults use the [slim HUD and generated Sable art](SLIM_HUD.md). Historical art budgets below describe the beta.6 release where noted.

# Sable Outpost — visual implementation

This page describes the legacy beta.6 default. The separate [compact HUD and animated sprite candidate](SABLE_V2.md) documents its expanded viewport and allocations.

The environment, actors, weapon and interface share one original native-pixel art direction. The level retains its safe start, meaningful gates, combat partition and marked exit. Collision topology is unchanged; all sixteen fixtures are decorative.

| Visual signal | Meaning |
|---|---|
| Gunmetal blue-grey | Structural walls |
| Muted desaturated green | Machinery surfaces |
| Teal panels, pale cyan edges and access emblem | Functional sliding door |
| Amber caged lamp or sector marking | Local landmark |
| Red armour | Hostile Sentinel |
| Green/cream medical crate | Healing pickup |
| Pale cyan beacon | Unlocked exit |

Ceiling and floor remain distinct flat tones. There are no eye-height rails, repeated screen-space texture rows or material-driven false corners. Surface palette changes remain separate from physical segment identity.

## Wall-mounted detail

`levels/living_world.json` authors wall cell, exposed side and fixture kind. The compiler rejects empty cells, buried faces, incorrectly oriented door fixtures and excess content. Records compile to sixteen-byte resident entries; art stays in the cold asset bank.

Fixtures share the camera transform, project at the upper quarter of the wall and use 16×16, 8×8 and 4×4 cels. A compressed 8×16 variant covers oblique close views; tangent close views are suppressed. These discrete LOD billboards approximate wall decals; they are not arbitrary perspective-correct UV textures. Very distant details disappear.

Every submitted eight-pixel strip must match both the physical wall segment and its along-face map cell. Door emblems move with the sliding panel and disappear into the jamb. Actors and the exit submit first. Decorations may consume at most four remaining OAM entries, subject to the same sixteen-world-object/four-per-scanline admission limits.

A temporary 256-byte visibility table borrows the completed world-copy staging buffer at $C900. Snapshot copying has finished, and no simulation yield occurs inside fixture rendering. This avoids repeatedly searching all 80 rays and preserves the wall attribute packet for cached updates without another permanent allocation.

## HUD and native graphics budget

| Physical range | VRAM bank | Use |
|---|---:|---|
| $8000–$81FF | 0 and 1 | Double-buffered masked world objects, 32 patterns per page |
| $8200–$86DF | 0 | 78 HUD patterns, including ten two-tile digits |
| $86E0–$87FF | 0 | 18 spare HUD patterns |
| $8400–$853F | 1 | Shotgun, reticle and flash, 20 patterns |
| $8800–$97FF | 0 and 1 | Signed world patterns, including the complete wall atlas |

The world uses signed BG addressing. LYC=96 triggers a short STAT handler that enables unsigned BG addressing before the first HUD tile fetch. VBlank restores signed addressing. Only the addressing bit changes; the selected world page remains intact. This gives the bottom 160×48 panel an independent vocabulary while retaining the 160×96 viewport.

Health and remaining hostiles use 8×16 digits. Exit state is literal LOCK, OPEN, DEAD or DONE. The central helmet portrait is static. The footer shows A FIRE / B USE; Start restarts after death or completion. No menu, inventory or save system is implied.

The source bank contains 118 entity/fixture patterns, but only masked pairs selected for the current frame enter the 32-pattern VRAM pool. All native art is authored in `artwork.py`; no external game's assets are used.

## Publication and evidence

Eleven HUD tile IDs are prepared in WRAM before waiting for VBlank. The display window performs bounded tile writes, graphics transfers, OAM DMA and page selection. Single-window dynamic-plus-mask work is capped at 24 patterns. Larger default packets stage over two VBlanks, with at most 96 blocks first and 80 last. Optional reprojection reserves another window for exceptionally large OBJ packets because it also copies published object coordinates.

For an exact wall-cache hit, independent OBJ ownership permits a single-VBlank upload of at most 32 masked patterns plus HUD/OAM. The BG viewport is untouched; its page need not match the published OBJ bank. Sequential HUD packet reads save 76 CPU cycles in the publication window. See [wall reuse](WALL_REUSE.md).

The HRAM OAM routine uses the documented 40-iteration, four-M-cycle loop: 160 M-cycles total. Boundary tests require publication before scanline 153, accounting conservatively for CGB's early LY reset. These constraints were verified in the project harness and the final independent emulator lanes.

Primary hardware references: [Pan Docs LCDC](https://gbdev.io/pandocs/LCDC.html), [STAT](https://gbdev.io/pandocs/STAT.html), [OAM DMA](https://gbdev.io/pandocs/OAM_DMA_Transfer.html). Source text was checked in the gbdev/pandocs repository at `fe246067b695b5404a4a6a47efb4fd6d921ececb`.

Nine coherence captures were visually inspected before accepting `playtests/v070_sable_capture_pixels.json`. `playtests/sable_art_tour.json` covers near and oblique vents, lighting, sector signage, the starting door and a Sentinel. Functional checks include exact wall descriptors/tiles, segment/cell masks, HUD VRAM bounds, raster-vector timing, packet snapshots, object capacity and controller-only completion. See [the candidate evidence](TEST_REPORT.md).

The arithmetic and [wall-reuse passes](WALL_REUSE.md) retain the same artwork and reviewed pixels. Acceptance ceilings remain 1.05 million coherence-mean cycles and 2.2 million combat-maximum cycles. Geometry, byte exactness, overflow and timing gates were not relaxed. Physical CGB, flash-cartridge and human LCD/readability validation remain pending.
