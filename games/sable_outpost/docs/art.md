# Sable Outpost: v0.8 art and animation

The environment, actors, shotgun and steel HUD share an industrial science-fiction direction. (The weapon cels were later replaced by renders of 3D models, `docs/reference/asset-formats.md`; the generated shotgun master is retained as a design source.) The first sector is the outpost itself: a safe start in the landing airlock, a decon passage, the bunk room, the mess hall and the comms room where the Sentinel guards the lift, behind four sliding doors, with a healing pickup and a marked exit (`games/sable_outpost/docs/campaign.md`, "Named places"). Sixteen wall fixtures add landmarks without changing collision geometry.

## Visual language

| Signal | Meaning |
|---|---|
| Blue-grey steel | Structural walls |
| Muted green | Machinery surfaces |
| Teal panels and pale cyan edges | Functional sliding doors |
| Amber lights and sector marks | Local landmarks |
| Red armour | Hostile Sentinels |
| Green medical crate | Healing pickup |
| Exit beacon | Available level exit |

The ceiling and floor stay visually distinct. There are no eye-height rails, material-colour false corners or repeated screen-space texture bands. Physical segment identity remains independent of surface colour.

## Native sprite sources

Selected generated masters, prompts, palettes, indexed PNGs, anchors and frame metadata live in `games/sable_outpost/art/`. `games/sable_outpost/art/tools/adapt_sable_art.py` is an offline authoring step; builds consume the versioned PNGs and never generate images. `sprite_assets.py` validates binary transparency, palette indices, dimensions and source hashes before 2bpp compilation.

| Asset | Native size | Cels |
|---|---|---:|
| Shotgun | 40×32 | 4: idle, recoil, pump back, pump forward (rendered from a 3D model, `docs/reference/asset-formats.md`) |
| Muzzle flash | 8×16 | 2 |
| Sentinel | 16×32, 8×16, and a 4×8 figure in an 8×16 cel | 12 per size: idle, walk, attack, hurt, death. Each size is half the one before, so an enemy grows steadily as it approaches; the smallest is derived from the 8×16 by `art/tools/derive_distant_sentinel.py`. The earlier 16×16 middle cel (`native/sentinel_mid.png`) is kept but no longer drawn: at the height of the 8×16 it stopped enemies growing between 1¾ and 4 cells. |
| Player helmet | 16×16 | 4: normal, blink, hurt, dead |
| Reticle | 8×16 | 1 |
| Steel panel | 160×24 | Static base with dynamic tile regions |

The current helmet is the armoured, narrow-visor portrait retained after review. Its authored source is `steel_hud.py`. Preserve that selected face when editing the interface. The skull counts **living enemies remaining**; the objective reads **GOAL/HUNT**, then **GOAL/EXIT**. DEAD/DONE clear GOAL. See [HUD implementation](steel-hud.md).

## Animation and gameplay

Accepted simulation ticks enter immutable render snapshots. Walking phases last eight ticks; idle motion is slower. Attack, hurt and firing select short reactions. Accepted shots restart recoil, and pending flashes survive until they can be published. The resident weapon's cels (streamed in with the LCD off on a swap) animate through OAM references, without per-frame weapon-pattern uploads.

Death animation is cosmetic: enemy death, pickup availability and exit activation happen immediately. Three death poses span roughly 0.6 simulation seconds where capacity permits. Living actors and gameplay pickups take priority over cosmetic corpses. Visible animation cadence depends on full or cached presentation timing; the experimental fast foreground lane remains disabled.

## Graphics and publication budgets

| Resource | v0.8 allocation |
|---|---|
| World / HUD | 160×120 / 160×24; horizon 60, STAT split at line 120 |
| HUD patterns | 94 of 96, bank 0 $8200–$87DF |
| Weapon, reticle and flash | 86 preloaded patterns, bank 1 $8200–$875F |
| Enemy and fixture ROM dictionary | 218 source patterns, before runtime masks |
| Masked world OBJ patterns | 32 per VRAM bank, $8000–$81FF |
| World admission | 16 objects; four per scanline; hardware limit ten per line |
| Dynamic BG patterns | 96 |
| HUD packet | 16 bytes, including six portrait tile IDs |
| Full packet | At most 176 DMA blocks, staged across two or three VBlanks |

Pattern source indices and resident VRAM tile IDs are different domains. The lowered objective text uses vertically paired preloaded patterns; ID+1 supplies the last text row and chassis rail. That adds 108 CPU T-cycles per HUD publication and no DMA blocks.

Fixtures project at the upper quarter of a wall, use discrete size levels, and require matching physical segment and along-face cell identity. Door emblems move with the finite panel. Fixtures are bounded billboards, not arbitrary perspective-correct textures, and consume at most four remaining world OAM entries after higher-priority objects.

## Verification and history

The hash oracles are retired: the v0.9 oracle (`games/sable_outpost/playtests/archive/oracles/sable_v09_capture_pixels.json`) and the v0.8 fixture (`sable_objective_spaced_capture_pixels.json`) are kept as evidence, and current captures are golden snapshots ([verification](../../../docs/explanation/verification.md)). Asset checks cover all 36 enemy cels, weapon phases, portrait states, clocks, mask admission, both HUD maps, text spacing and maximal publication. Real ROM captures are reviewed separately from generated concepts.

See [the current qualification](../../../docs/evidence/TEST_REPORT.md), [architecture](../../../docs/explanation/architecture.md), and the preserved [beta.6 art contract](../../../docs/archive/SABLE_OUTPOST_BETA6.md). Physical hardware is unavailable; results are emulator-qualified.
