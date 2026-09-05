# Lupine 3D 0.7.0-beta.3 test report

Candidate ROM SHA-256:
`0890469007ab8d470d15c07d95a319c9565b27df8d40ca0511572aefe41754a3`

4 MiB MBC5 · CGB-only · no cartridge RAM · **physical hardware not tested**

## Automated contracts

**75 tests pass locally.** This includes frozen v0.1 hash, deterministic builds, cartridge layout, projection and product arithmetic, generated-code/host descriptors, tile/map bytes, all door-state face IDs, combat, input, publication, colour metadata and memory bounds.

Three runtime tests cover bounded quotient/remainder/overflow behavior, every product-bank selector with both address-half boundaries, and Q14 continuation versus full restart over 512 open-room ray probes. The latter explicitly requires late ambiguous crossings. The unchanged resident-memory reserve gate still requires at least 3,000 bytes.

Eight art/UI acceptance tests cover the 78-pattern HUD dictionary, actual line-96 interrupt/vector timing, prepared HUD snapshot bytes and status text, fixture authoring legality, segment-plus-cell masks, upper-wall placement and projection preservation, publication-budget boundaries before line 153, and actor-priority scanline capacity.

New coverage exercises:

- all 61,696 supported camera records' Q14 component-error certificates, including centre hitscan;
- 64 retained severe rays in actual ROM code;
- 1,600 ROM/host sliding-door probes across four doors and five apertures;
- shared aperture LOS versus radius collision;
- 16-bit timestamp wrap, repeated edges, bounded debt and non-overwriting overflow;
- immutable rendering while live simulation advances;
- fixed movement under different service batching;
- per-bit OBJ masks, three-LOD hysteresis and scanline admission;
- two actor slots, nearest-first shots and all-dead exit unlock;
- surface-profile legality and exact hidden attributes;
- bulk-copy lengths/guards and immutable reprojection coordinates.
- forced maximum 176-block staged publication and Start-to-restart after death/completion.

## Current routes

| Measurement | Coherence tour | Combat diagnostic |
|---|---:|---:|
| Updates / captures | 11 / 9 | 47 / 14 |
| Mean CPU cycles/update | 980,901.818 | 1,218,677.191 |
| Maximum CPU cycles/update | 1,265,016 | 1,685,836 |
| Minimum visual updates/s | 6.6312 | 4.9759 |
| Peak dynamic patterns | 18 / 96 | 24 / 96 |
| Peak total casts | 56 | 59 |
| Peak visible OAM | 11 / 40 | 15 / 40 |
| Peak Y-selected scanline OAM | 4 / 10 | 7 / 10 |
| Unsafe GDMA starts | 0 | 0 |
| Frozen RGB captures | 9 / 9 exact | None |

Cycles include publication waits and concurrent simulation work. These are project-harness CPU-cycle measurements, not measurements from an original CGB. Live actor poses can differ as render duration changes; the separate frozen-world comparison isolates the optimization's exact output and timing.

The nine Sable RGB fixtures were accepted after the art pass's visual inspection in `playtests/v070_sable_capture_pixels.json`. This performance pass changes none of them. A separate frozen-simulation folded/unfolded comparison matches all nine RGB images exactly. The six-view art tour separately covers close and oblique vents, lighting, a sector sign, the airlock and the Sentinel.

The gameplay diagnostic teleports its camera for state coverage. It explicitly aims at the live enemy and relocates to the actual drop; it does not inject health/death/completion. All states are reached by generated gameplay code.

Across 53 identical frozen scenes, mean update cycles fall 8.73% and wall-casting cycles fall 10.56% against the preserved beta.2 ROM. All compared pair/physical descriptors, surfaces, generated tiles, full maps/attributes, masked objects, HUD packets and RGB remain exact. Current content budgets stay at 1.05 million coherence-mean cycles and 2.2 million combat-maximum cycles; memory, correctness and hardware-timing gates were not relaxed. See [runtime evidence](RUNTIME_PERFORMANCE.md).

## Controller-only level completion

**236 completed updates**, 84 health remaining, Sentinel dead, medkit collected and exit reached. No pose or gameplay RAM injections. Every completed update validates descriptors, depths, segments, masks' surrounding wall packets, surface attributes, OAM limits, queue overflow and publication safety. More completed renders do not imply a longer elapsed playthrough: the controller samples the live world after each render.

The bot reads live state to steer. This proves functional controller completion, not blind human navigability or player preference.

## Geometry-tail laboratory

The retained renderer-benchmark level was rescanned at 381 positions and 64 angles: **24,384 views / 3,901,440 physical columns**.

| Result | Current scan |
|---|---:|
| Maximum wall-top error | 4.489522 px |
| Columns with error ≥8 px | 0 |
| Wrong-segment columns | 67 |
| Wrong-material columns | 3 |

The historical 41-pixel corpus remains unchanged. Its 64 retained severe ray cases now choose the floating oracle's hit cell and axis in actual generated code. The full scan is a host comparison, not 24,384 independent-emulator frames. Q14 fixes crossing order; Q5 projection and adaptive interpolation remain quantized.

Artifacts: `build/q14_tail.json`, `.csv`, `.png`.

## Independent emulators

| Core / model | Pin | Result for candidate SHA |
|---|---|---|
| SameBoy CGB-0 | `213a12ce93d66b105a113debd9396306066a7cfc` | Pass |
| SameBoy CGB-E | same pin | Pass |
| mGBA CGB | `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6` | Pass |

Each lane runs 480 LCD frames, observes 62 page swaps, moves/turns and opens the starting door using input. Startup RGB, including the split-screen HUD and door emblem, matches the project host under matching linear RGB15 conversion.

SameBoy observes 183 GDMA starts per model, zero unsafe starts and zero unsafe page flips. mGBA verifies boot/control/RGB and zero input overflow but **does not instrument DMA writes**. SameBoy uses an original synthetic bootstrap; mGBA uses built-in skip-BIOS. Neither tests the Nintendo boot ROM.

CI configuration includes both pinned cores, gameplay completion and variant checks. These are local executed results; no new remote CI execution is claimed.

## Variant and resource acceptance

- Two-Sentinel scene: eight world objects, 17 visible OAM total, six objects maximum per scanline.
- Masked 8×16 allocation: ≤16 world entries, ≤32 mask patterns, ≤4 world objects per scanline.
- Forced large packet tests keep prior OAM until final BG/attribute/HUD/OAM publication.
- Optional reprojection: exact clamp, static UI, published-world X shifts, future-shadow isolation and matching guard attributes pass in the project harness. Default remains off; independent/hardware perception testing is not claimed.
- Resident image: 29,309 bytes, end $73CD, 3,123 bytes free below $8000. Grouped division temporarily adds two stack bytes; no new HRAM or VRAM allocation.
- Cold assets: 9,258 bytes in bank 156; Q14 tables: 262,144 bytes; products: 131,072 bytes.
- Stack: fixed $CFFF with 512 bytes reserved. HRAM: 111 state bytes plus separate ten-byte DMA stub.
- Packet maximum: 176 blocks, staged into ≤96 and ≤80 blocks when needed. Single-window dynamic-plus-mask cap is 24; optional reprojection may use an extra window for large masked packets.
- HUD: 78 of 96 available bank-0 patterns; fixtures: 16 authored, at most four OAM entries per frame from the existing world capacity.

## Remaining acceptance boundary

No original CGB or flash cartridge was available. No unlimited-input guarantee after queue overflow, arbitrary-precision depth, arbitrary sprite scaling, or default-enabled reprojection is claimed. See [implementation status](OVERHAUL_IMPLEMENTATION.md) and [hardware checklist](HARDWARE_TEST_CHECKLIST.md).
