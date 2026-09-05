# v0.7.0-beta.4 — Wall reuse and combat presentation

This document preserves the beta.4 milestone measurements. See [streaming columns and prepared rays](COLUMN_PERFORMANCE.md) and the [current test report](TEST_REPORT.md) for the active candidate.
All four implementation steps are delivered. An unchanged wall view now remains in VRAM while actors, pickups, fixtures, weapon feedback and HUD are rendered from the next immutable world snapshot. Changing the camera or any wall input returns to the full renderer.

Candidate ROM SHA-256: `8813ab38201f937c18c9b15e26d58c94fe2e873bbaf900a358fcf933fef34e0b`.

## 1. Exact wall-view reuse

`wall_cache.py` compares 290 bytes; it uses neither a hash nor a pose tolerance.

| Compared input | Bytes |
|---|---:|
| Q8 camera X/Y and angle | 5 |
| VRAM profile and world mode | 2 |
| Door count | 1 |
| All four door records, including opening fractions | 24 |
| Content/VRAM reload generation | 2 |
| Complete active map | 256 |

Cheap pose fields are compared first. Any mismatch captures a new key **before** casting or yielding and clears its validity. Only a completed full publication makes that key reusable. The next snapshot must match it exactly. Every map byte matters, including doors outside the current field of view; this is deliberately conservative.

`load_level` and `init_vram` invalidate the cache and advance the 16-bit generation. Thus a reload during a yielding render cannot certify the old frame as the new world. Counter wrap and in-flight invalidation have actual-program tests. Future mutable palette, material, fixture or banked-content loaders must call the same invalidation routine; current surface and fixture metadata is immutable ROM data.

Health, actor motion/animation, firing, pickup state and exit status do not invalidate wall geometry. Their renderers still run. Fractional camera movement, turning, any door fraction/state and map edits do invalidate it. A stationary player watching a moving door receives full renders until its geometry stabilizes.

## 2. Entity/HUD-only updates

After snapshot capture, a hit skips `cast_all`, `render_view`, guard preparation and BG attribute generation. It retains all 80 depth/segment records, 160 physical columns, dynamic patterns and complete wall map/attributes. The entity renderer reprojects and masks the current actor state against that retained, matching wall depth.

Fixture visibility now borrows the completed world-copy staging buffer at $C900. It previously overwrote the future attribute packet. Snapshot copying has finished and no simulation yield occurs inside entity/fixture rendering, so this scratch lifetime preserves the cached attribute bytes without another allocation or copy.

Prepared HUD values and shadow OAM belong to the same snapshot as the newly masked sprites. The fast publication transfers zero to 32 OBJ patterns, updates eleven HUD IDs in both maps, performs OAM DMA and finishes within one VBlank. It never uploads wall patterns, wall attributes or viewport tile IDs, and never flips LCDC's BG map bit.

## 3. Independent sprite ownership

`CURRENT_PAGE` owns the visible BG page. New `OBJ_PAGE` owns the published masked-object bank. Every update writes masked patterns to `OBJ_PAGE ^ 1` and gives its shadow objects that bank bit. Only final publication changes the owner.

Cached updates can therefore alternate sprites repeatedly while keeping the BG page fixed. A subsequent full render can target a different BG bank and OBJ bank safely: their physical pattern ranges do not overlap. The old complete OAM packet stays visible until its replacement's patterns are ready.

Full packets retain the maximum 176-block contract: at most 96 blocks in the staging VBlank and 80 in the final VBlank. No safety threshold was widened. Eleven sequential HUD packet loads save 76 CPU cycles in the critical window, making room for ownership and completion bookkeeping while keeping the existing pre-line-153 boundary tests green.

`PRESENT_SERIAL` increments after either publication path. Tools count these completed presentations separately from physical BG page flips. The eight-bit serial can wrap; the harness counts write events and the mGBA adapter accumulates modulo-256 differences. A sprite-only presentation is never reported as a new geometry render.

| Additional WRAM | Allocation |
|---|---:|
| Map key at $CD00–$CDFF | 256 bytes |
| Metadata key at $DF20–$DF41 | 34 bytes |
| Owners, flags, serial and generation at $C8B3–$C8B9 | 7 bytes |
| **Total** | **297 bytes** |

The existing 512-byte stack reservation, 111-byte HRAM state and ten-byte DMA stub remain intact. No VRAM or cartridge bank is added. Moving the cold startup map into bank 156 and placing unaligned fixture records after hot tables preserves **3,123 free resident bytes**; cold assets now total 9,514 bytes.

## 4. Measurements and acceptance

The archived beta.3 comparison ROM has SHA `0890469007ab8d470d15c07d95a319c9565b27df8d40ca0511572aefe41754a3`.

The benchmark first checks 53 frozen scenes: the coherence/art poses and both approaches to all four doors at five apertures. Each scene has a warm full frame followed by either a cached update or a forced full update of the same snapshot. RGB, descriptors, masks, dynamic tiles, map, HUD and OAM match exactly. Attribute bank bit 3 is normalized because independently selected BG pages are intentional; all palette/flip semantics and each actual published bank are separately checked.

Mean frozen update cost is **135,879 cached versus 1,229,561 full cycles**, including waits: an **88.95% reduction for an already reusable view**. This is not the improvement during movement or a whole-game frame-rate claim.

A separate fresh full-render comparison against beta.3 covers the same 53 scenes: mean cost rises from 1,218,900 to 1,234,852 cycles (**1.31%**) to capture/check the key. All RGB, geometry, wall packets, mask patterns and visible OAM remain exact. This cross-version comparison normalizes only the stale bank bit in disabled Y=0 OAM slots, which can differ because boot now owns an independent OBJ page. It does not normalize enabled sprites or their other attributes. The cached/full comparison within beta.4 compares every OAM byte without that normalization.

The live trials advance the LCD frame counter by 72 after a common warm-up, with fixed simulation enabled. Because measurement begins in VBlank, their elapsed interval is approximately 1.19 seconds. Initial combat pose/clock setup is explicitly injected; thereafter only LCD-timed controller signals are supplied. Three one-frame A pulses occur at frames 8, 32 and 56. These are deterministic phase samples, not a latency distribution over every possible input phase.

| Live trial | Archived beta.3 | Candidate forced full | Candidate wall reuse |
|---|---:|---:|---:|
| Idle presentations/s | 5.89 | 5.89 | 59.71 |
| Stationary combat presentations/s | 6.73 | 6.73 | 40.37 |
| Combat mean GDMA blocks/update | 63.25 | 63.25 | 8.25 |
| Fire → packet publication | 150.43–150.48 ms | 150.43–150.48 ms | 49.48–49.52 ms |
| Fire → next muzzle scanline opportunity | 156.77 ms | 156.77 ms | 56.32 ms |
| Turning trial full geometry updates | 8 | 8 | 8 |
| Turning trial additional reused updates | 0 | 0 | 8 |

The muzzle-scanline metric adds the time until the next scan of the sprite's first row. It is an emulator timing estimate, not a photodiode measurement, original LCD response or subjective assessment. The cached combat trial presents eleven visible animation changes; the slower paths sample the looping animation at the same phase. No input queue overflow occurs.

The moving camera still costs a full render. In the fixed-duration turning trial, eight genuine geometry updates occur in every mode; the candidate also presents eight reused updates during stable poses. Do not call that doubled turning FPS. The mixed combat diagnostic retains a worst update of 1,685,828 cycles, approximately 4.98 full updates/s.

The separate 47-update combat route contains 22 full and 25 cached updates, averaging **692,666 cycles**. Its changing live actor snapshots make it a gameplay diagnostic, not an exact scene-for-scene speed comparison. The controller-only route completes the level in 233 presentations with 84 health, no RAM injections, no overflow and no unsafe GDMA.

## Verification boundaries

- **80 automated tests** include all 290 independently mutated key bytes, actor-only hits, fractional-pose/door misses, reload generation/wrap, cached/full transitions, zero-to-maximum sprite packets, serial wrap and unchanged memory reserves.
- All nine accepted Sable RGB hashes remain untouched. Folding on/off and reuse on/off produce the same nine images.
- The project harness checks actual displayed VRAM, admitted OAM bank bits and uploaded masked patterns, in addition to host descriptors and staging buffers.
- SameBoy CGB-0 and CGB-E each run 480 LCD frames: 270 presentations, 243 cached, 27 BG flips, zero unsafe GDMA/OAM starts, zero unsafe presentations and zero writes into visible mask banks.
- mGBA runs 480 LCD frames: 272 presentations, 27 BG flips, passing startup RGB, controller/door checks and zero input overflow. Its adapter does not instrument DMA writes. The two extra presentations reflect different bootstrap timing.
- Exact original CGB/flash-cartridge acceptance remains pending. Neither independent lane tests the Nintendo boot ROM.

## Reproduce

```sh
make test
make playtest playtest-world playtest-art playthrough variants
make wall-reuse
python3 tools/profile_rendering.py --output build/profile_reuse.json
```

`make wall-reuse` compares the candidate's cached and forced-full paths without requiring an old ROM. CI runs it and preserves its result. To add the archived baseline, build beta.3 in a separate checkout and supply both its ROM and symbols:

```sh
python3 tools/benchmark_wall_reuse.py \
  --baseline-rom /path/to/beta3/lupine3d.gb \
  --baseline-symbols /path/to/beta3/lupine3d.sym
```

`LUPINE3D_WALL_REUSE=0` builds the full-render diagnostic variant. `WALL_CACHE_DISABLE` at $C8B7 provides a runtime A/B within the default ROM; it is a test switch, not a player setting. Matching host flags remain required for build variants.

Candidate-bound evidence: [wall reuse measurements](../research/results/wall_reuse_beta4.json) and [test report](TEST_REPORT.md). The earlier arithmetic implementation remains documented separately in [runtime performance](RUNTIME_PERFORMANCE.md).
