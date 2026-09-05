# Lupine 3D 0.7.0-beta.2 test report

Candidate ROM SHA-256:
`0ce5bc301d5b8cd67dc42de710e1c9a3db6cc63314cf323fb59b55659c0d08e1`

4 MiB MBC5 · CGB-only · no cartridge RAM · **physical hardware not tested**

## Automated contracts

**72 tests pass locally.** This includes frozen v0.1 hash, deterministic builds, cartridge layout, projection and product arithmetic, generated-code/host descriptors, tile/map bytes, all door-state face IDs, combat, input, publication, colour metadata and memory bounds.

Eight art/UI acceptance tests cover the 78-pattern HUD dictionary, actual line-96 interrupt/vector timing, prepared HUD snapshot bytes and status text, fixture authoring legality, segment-plus-cell masks, upper-wall placement and projection preservation, publication-budget boundaries before line 153, and actor-priority scanline capacity.

New coverage exercises:

- all 61,440 supported camera records' Q14 component-error certificates;
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
| Mean CPU cycles/update | 1,006,437.091 | 1,287,407.319 |
| Maximum CPU cycles/update | 1,265,024 | 2,105,892 |
| Minimum visual updates/s | 6.6312 | 3.9834 |
| Peak dynamic patterns | 18 / 96 | 24 / 96 |
| Peak total casts | 56 | 59 |
| Peak visible OAM | 11 / 40 | 15 / 40 |
| Peak Y-selected scanline OAM | 4 / 10 | 7 / 10 |
| Unsafe GDMA starts | 0 | 0 |
| Frozen RGB captures | 9 / 9 exact | None |

Cycles include publication waits and concurrent simulation work. These are project-harness CPU-cycle measurements, not measurements from an original CGB. The beta is not a blanket throughput improvement: true panel intersection, fixed simulation, attributes and masked sprites add work.

The nine Sable RGB fixtures were accepted after visual inspection in `playtests/v070_sable_capture_pixels.json`. New palettes, art, fixtures and HUD intentionally change the RGB image; the existing wall descriptor/compositor contracts remain exact. A separate frozen-simulation folded/unfolded comparison matches all nine RGB images exactly. The six-view art tour separately covers close and oblique vents, lighting, a sector sign, the airlock and the Sentinel.

The gameplay diagnostic teleports its camera for state coverage. It explicitly aims at the live enemy and relocates to the actual drop; it does not inject health/death/completion. All states are reached by generated gameplay code.

The visual pass increases mean work by approximately 9.5% on the coherence route and 3.6% on the combat diagnostic. Safety staging can also add a refresh interval at a threshold. Current content budgets are explicitly 1.05 million coherence-mean cycles and 2.2 million combat-maximum cycles; correctness and hardware-timing gates remain strict. Fixtures reuse transient attribute memory for a visibility lookup and reject invisible records before copying/projecting them.

## Controller-only level completion

**226 completed updates**, 84 health remaining, Sentinel dead, medkit collected and exit reached. No pose or gameplay RAM injections. Every completed update validates descriptors, depths, segments, masks' surrounding wall packets, surface attributes, OAM limits, queue overflow and publication safety.

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

Each lane runs 480 LCD frames, observes 61 page swaps, moves/turns and opens the starting door using input. Startup RGB, including the new split-screen HUD and door emblem, matches the project host under matching linear RGB15 conversion.

SameBoy observes 178 GDMA starts per model, zero unsafe starts and zero unsafe page flips. mGBA verifies boot/control/RGB and zero input overflow but **does not instrument DMA writes**. SameBoy uses an original synthetic bootstrap; mGBA uses built-in skip-BIOS. Neither tests the Nintendo boot ROM.

CI configuration includes both pinned cores, gameplay completion and variant checks. These are local executed results; no new remote CI execution is claimed.

## Variant and resource acceptance

- Two-Sentinel scene: eight world objects, 17 visible OAM total, six objects maximum per scanline.
- Masked 8×16 allocation: ≤16 world entries, ≤32 mask patterns, ≤4 world objects per scanline.
- Forced large packet tests keep prior OAM until final BG/attribute/HUD/OAM publication.
- Optional reprojection: exact clamp, static UI, published-world X shifts, future-shadow isolation and matching guard attributes pass in the project harness. Default remains off; independent/hardware perception testing is not claimed.
- Resident image: 29,053 bytes, end $72CD, 3,379 bytes free below $8000.
- Cold assets: 9,258 bytes in bank 156; Q14 tables: 262,144 bytes; products: 131,072 bytes.
- Stack: fixed $CFFF with 512 bytes reserved. HRAM: 111 state bytes plus separate ten-byte DMA stub.
- Packet maximum: 176 blocks, staged into ≤96 and ≤80 blocks when needed. Single-window dynamic-plus-mask cap is 24; optional reprojection may use an extra window for large masked packets.
- HUD: 78 of 96 available bank-0 patterns; fixtures: 16 authored, at most four OAM entries per frame from the existing world capacity.

## Remaining acceptance boundary

No original CGB or flash cartridge was available. No unlimited-input guarantee after queue overflow, arbitrary-precision depth, arbitrary sprite scaling, or default-enabled reprojection is claimed. See [implementation status](OVERHAUL_IMPLEMENTATION.md) and [hardware checklist](HARDWARE_TEST_CHECKLIST.md).
