# Lupine 3D 0.6.0 test report

**Software target:** CGB-only, 4 MiB MBC5, no cartridge RAM<br>
**Physical hardware tested:** no

## Automated result

All **34 tests pass**. They cover:

- Nintendo logo, CGB/MBC5/ROM-size fields, version byte and checksums;
- deterministic 4 MiB output and the frozen reference-ROM SHA-256 oracle;
- HRAM/OAM-DMA separation and MBC5 projection/product/atlas placement;
- exact signed-error DDA against host probes;
- exact 80-ray top/style/face/along/depth/segment records;
- exact 160-column reconstruction, edge recasts and event grammar;
- exact atlas signatures, both VRAM profiles and generated entity art;
- the authored map, compiled level header and stable surface segments;
- generated tile bytes and complete 384-byte hidden map;
- more than 2,000 exhaustive map/angle guardrail views;
- forced 120-block single-VBlank publication and deferred OAM DMA;
- OAM total/per-scanline capacity and wall-depth clipping;
- radius collision and an eight-step collision-preserving door;
- Sentinel line of sight, chase, attack, hitscan damage, death and drop;
- medkit collection, exit activation and level completion;
- VBlank input latching during long renders;
- compile-time reprojection clamp, edge guards, page reset and HUD split;
- the retained 41-pixel rare-tail pose/surface/neighborhood certificate;
- feature-aware hot-path and complete-update cycle ceilings.

## Empty-world exact-output route

| Measurement | Result |
|---|---:|
| Updates | 27 |
| Captures | 9 |
| Mean cycles/update | 972,626.963 |
| Maximum cycles/update | 1,124,336 |
| Minimum updates/s | 7.4609 |
| Maximum dynamic tiles | 50 / 96 |
| Maximum total casts | 59 |
| Maximum visible OAM | 18 / 40 |
| Maximum OAM per scanline | 4 / 10 |
| Unsafe GDMA starts | 0 |
| Failed checks | 0 |
| Frozen RGB captures | 9 / 9 exact |

This route runs in `WORLD_MODE_EMPTY`. It proves that the gameplay expansion does not change any accepted wall descriptor, tile byte, hidden map byte or final RGB pixel.

## Living World route

| Measurement | Result |
|---|---:|
| Updates | 8 |
| Captures | 6 |
| Mean cycles/update | 859,909 |
| Maximum cycles/update | 1,125,772 |
| Minimum updates/s | 7.4514 |
| Maximum dynamic tiles | 38 / 96 |
| Maximum total casts | 55 |
| Maximum visible OAM | 26 / 40 |
| Maximum OAM per scanline | 5 / 10 |
| Unsafe GDMA starts | 0 |
| Failed checks/state assertions | 0 |

The route sees the Sentinel, lands three edge-separated shots, verifies health transitions, verifies death/drop/exit activation, collects the medkit, and enters the active exit.

## Research gates

- geometry corpus: 24,384 views / 3,901,440 physical columns;
- entity atlas: 80 patterns, 255 exact signatures, 41 freed tile IDs;
- entity-atlas maximum dynamic count: 58 / 96, zero overflow views;
- renderer atlas: 121 patterns and 255 exact signatures;
- projection LUT: 2,359,296 exact bytes across 144 MBC5 banks;
- DDA product LUT: 65,536 exact bytes across four MBC5 banks;
- rare tail: 1,566 columns at or above eight pixels, all segment-selection events;
- rejected correction experiment: one changed/improved column out of 3,901,440;
- resident engine: 29,949 bytes, ending at `$764D`;
- hot HRAM: 111 bytes at `$FF80–$FFEE`, separate from the `$FFF4` DMA stub.

## Remaining acceptance work

The project harness is deterministic and cycle-aware but is not an independent emulator. The exact candidate ROM must still pass maintained external emulators and an original CGB using a 4 MiB MBC5-capable flash cartridge. Complete `docs/HARDWARE_TEST_CHECKLIST.md` before claiming hardware certification.
