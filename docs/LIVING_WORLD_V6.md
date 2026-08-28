# Living World architecture

Lupine 3D 0.6.0 adds the first complete gameplay slice without weakening the accepted wall-rendering contract. The empty-world route still produces the same nine RGB captures; Living World state is exercised by a separate scenario.

## Frame ownership

The main loop owns simulation and the camera. VBlank owns only input sampling and optional display reprojection.

1. Consume one stable held/edge-latched input snapshot.
2. Apply radius-based movement or begin a door interaction.
3. Advance the door and low-frequency Sentinel simulation.
4. Cast walls into 80 ray records and reconstruct 160 physical columns.
5. Compose the hidden BG page.
6. Transform, depth-test and write entities into shadow OAM.
7. Wait for a fresh VBlank, commit BG tiles/map, publish OAM when safe, then flip pages.

No interrupt mutates the player pose, entity state, map, or descriptors during rendering.

## Geometry certificates

Each adaptive ray now produces two additional bytes:

| Buffer | Size | Meaning |
|---|---:|---|
| `RAY_DEPTH` | 80 bytes | Conservative corrected perpendicular distance in Q5 tiles |
| `RAY_SEGMENT` | 80 bytes | Stable ID for a contiguous exposed wall-face run |

Projection maps many Q5 distances to the same integer wall top. `top_depth_lut` stores the nearest member of that exact projection equivalence class. This is conservative for wall occlusion and avoids placing a divider in every ray.

Segment IDs are generated from the authored map. Safe midpoint interpolation requires matching face information and matching segment identity. A segment discontinuity forces an exact recast at the physical boundary.

The independent floating oracle still has one retained 41-pixel maximum caused by a quantized physical ray selecting a different surface. A full 3,901,440-column experiment found only one improvement from a proposed narrow correction, so the runtime does not include that heuristic.

## VRAM profiles

Static and dynamic wall vocabulary occupies tile IDs 0–198 in the entity-heavy scene. IDs 199–239 are reserved for Living World object art; 240–255 remain the weapon/HUD range.

| Profile | Atlas patterns | Entity patterns | Use |
|---|---:|---:|---|
| Renderer-heavy | 121 | 0 | Highest wall-cache coverage |
| Entity-heavy | 80 | 39 of 41 available IDs | Sentinel, medkit and hit effects |

Both atlas payloads and their exact signature dictionaries are stored in ROM. The build-selected active profile is resident; the inactive profile occupies a high ROM bank. Profile selection happens during level loading.

The entity atlas was trained over 24,384 views. It covers 38.909% of boundary-tile instances, has a maximum of 58 dynamic tiles, and has zero overflow views against the 96-tile capacity.

## OAM contract

The object layer uses a 160-byte shadow image at `$C800`.

| Entries | Owner | Capacity rule |
|---|---|---|
| 0–15 | 32×32 weapon | Never displaced by world actors |
| 16 | Crosshair | Never displaced |
| 17 | Muzzle flash | Never displaced |
| 18–39 | World entities/effects | Maximum 22 entries |

The current level has one actor, so its one-element submission list is already in depth order. Future multi-actor work must sort far-to-near before writing entries 18–39.

OAM is transferred only as a complete DMA image. When `DYN_COUNT > 72`, OAM DMA is deferred so the worst-case BG GDMA publication retains its VBlank guarantee. The next frame with sufficient budget publishes the newest complete shadow image.

The driven Living World route reaches 26 visible objects total and five objects on its busiest scanline, below the hardware limits of 40 and 10 respectively.

## Billboard projection and clipping

The Sentinel transform uses signed Q4 relative coordinates and the same 256-angle movement basis used by the player:

- forward = `(dx·cos + dy·sin) / 64`;
- lateral = `(-dx·sin + dy·cos) / 64`;
- screen X = `80 + lateral·127/forward`;
- entity depth = `forward·2` in Q5 tiles.

Actors behind the camera, outside the signed transform range, outside the projection range, or behind every relevant wall sample consume no OAM.

There are two size LODs:

- far: 8×16, two 8×8 objects;
- near: 16×32, two columns of four 8×8 objects.

Near billboards test the left and right eight-pixel strips separately against `RAY_DEPTH`. A hidden strip is omitted; a visible strip is submitted. This provides coarse wall clipping without runtime sprite scaling or BG tile recomposition.

## Sentinel simulation

The resident vertical slice supports six states: dormant, patrol, chase, attack, hurt and dead.

AI advances every fourth VBlank input sample rather than once per visual frame. Exact cell-space Bresenham traversal provides line of sight against the active WRAM map. The Sentinel patrols before acquisition, advances along its dominant cell delta while chasing, attacks at close range with a cooldown, uses a dedicated hurt cel, and activates its drop and the exit on death.

Player fire is a centre-screen hitscan guarded by the same successful entity projection and wall-depth visibility used for rendering. The Sentinel takes three hits. Its medkit is collected by cell overlap; the exit completes the level only after activation.

## Level format

`levels/living_world.json` uses `lupine-level-v1` and owns:

- dimensions and wall-material rows;
- player position and angle;
- door cell and orientation;
- entity position, health and activation radius;
- pickup source and value;
- triggers and exit cell;
- palette and VRAM profiles.

`tools/lupine3d_v4/levels.py` validates the authored data, generates surface segments, and emits a fixed 20-byte resident header plus the 256-byte active map. Additional levels can remain in MBC5 banks until a later transition loader copies one into WRAM.

## Physical interaction

Player collision is axis-separated and tests two leading-edge corners against a Q8 radius of `$38`. This keeps the camera away from wall planes and allows sliding along a free axis.

The authored door retains its solid map cell through eight opening steps. Its fraction advances by 32 per simulation update and retracts the projected panel before the cell is finally removed. Collision, wall rays and Sentinel line of sight therefore agree on when the passage becomes open.

## Optional micro-reprojection

Set `LUPINE3D_REPROJECTION=1` at build time to compile the experiment.

- A VBlank sample nudges `SCX` by one pixel from held turn input.
- Displacement clamps to ±4 pixels and decays toward zero without input.
- Guard tiles in columns 31 and 20 prevent exposed viewport edges.
- Exact page publication resets the displacement atomically.
- A STAT LYC interrupt at scanline 96 restores `SCX=0`, keeping the HUD fixed.

The default build leaves this disabled. It needs evaluation in multiple independent emulators and on an original CGB LCD before becoming a default presentation path.

## Acceptance evidence

The 0.6.0 software gate requires:

- all 34 unit and ROM-execution tests passing;
- nine empty-world RGB captures byte-exact;
- the Living World combat/pickup/exit scenario passing;
- exact depth and segment buffers on every driven update;
- zero dynamic-tile overflow and unsafe GDMA starts;
- OAM below total and per-scanline hardware limits;
- brief VBlank-sampled input edges surviving long renders;
- deterministic 4 MiB output and a clean-room exact rebuild.

Original-hardware acceptance remains pending and is intentionally tracked separately in `docs/HARDWARE_TEST_CHECKLIST.md`.
