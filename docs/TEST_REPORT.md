# Lupine 3D v0.4.0 test report

**Software verification target:** Game Boy Color, CGB-only, 4 MiB MBC5,
no cartridge RAM  
**Physical hardware tested:** no

## Automated result

All 25 tests pass. They cover:

- Nintendo logo, CGB/MBC5/ROM-size fields, version byte, and both checksums;
- deterministic 4 MiB output and the frozen v0.1.0 ROM SHA-256 oracle;
- HRAM ABI bounds and MBC5 projection/product table placement;
- exact signed-error DDA against host probes;
- adaptive 80-ray and final 160-column descriptors across a pose corpus;
- exact atlas signature reconstruction and mirrored VRAM contents;
- generated tile bytes and the complete 384-byte view map;
- exhaustive host guardrails over more than 2,000 map/angle views;
- the forced 120-block single-VBlank GDMA limit;
- coherent alternating pages, controls, collision, door, sound, and muzzle
  feedback;
- tightened isolated hot-path and complete-update cycle ceilings.

## Driven playtest

| Measurement | Result |
|---|---:|
| Updates | 27 |
| Captures | 9 |
| Mean cycles/update | 910,143.111 |
| Maximum cycles/update | 1,124,736 |
| Minimum updates/s | 7.4583 |
| Maximum dynamic tiles | 54 / 96 |
| Maximum total casts | 59 |
| Unsafe GDMA starts | 0 |
| Failed model checks | 0 |
| Exact v0.3.0 RGB captures | 9 / 9 |

Compared with the byte-exact v0.3.0 baseline, mean cycles improve 18.61%, the
maximum improves 11.08%, and the minimum update rate improves 12.45%.

## Research gates

- 24,384-view fidelity corpus: zero dynamic-tile overflows;
- exact tile atlas: 121 patterns, 255 signatures, 41.377% dynamic-instance
  coverage;
- projection LUT: 2,359,296 exact bytes across 144 MBC5 banks;
- DDA product LUT: 65,536 exact bytes across four MBC5 banks;
- resident engine: 27,645 bytes, ending at `$6D4D`;
- hot HRAM state: 104 bytes, `$FF80-$FFE7`.

The deterministic ROM SHA-256 for this source state is
`a3f17e45a6d0a3545a3ad03725b0352bbc40421ac17c0a4da65ed4be1654dd82`.
The release packager independently rebuilds the staged tree and the extracted
archive; its final report is authoritative if the source changes.

## Remaining acceptance work

The project harness is not an independent emulator. Complete
`docs/HARDWARE_TEST_CHECKLIST.md` in maintained external emulators and on an
original Game Boy Color with an MBC5-capable flash cartridge before claiming
hardware certification.
