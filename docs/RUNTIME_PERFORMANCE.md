# Gameplay performance implementation

This milestone resumes the engine overhaul after Sable Outpost. The foundation
already provides precision traversal, shared sliding-door geometry, fixed-tick
simulation, masked actors and coherent frame publication. The next target is
their cost in a populated level.

## Step-by-step contract

1. Preserve the accepted Sable ROM and symbols. Its SHA-256 is
   `0ce5bc301d5b8cd67dc42de710e1c9a3db6cc63314cf323fb59b55659c0d08e1`.
   Profile the existing coherence and combat routes before changing code.
2. Keep the door division's quotient and remainder in registers. Process four
   bits per loop, preserving the group counter on the stack. This removes
   intermediate quotient/remainder WRAM traffic while retaining ROM headroom.
   Preserve the unsigned overflow rejection contract.
3. At an uncertain crossing, continue in Q14 from the certified current cell.
   Preserve boundary distances and crossing count, compute the fine error once,
   and continue. Keep full initialization for coarse axial rays, casts starting
   in a door cell, and generic line-of-sight vectors.
4. Reduce product-table bank selection to three rotates and a mask. Preserve
   every table byte, product and bank-1 restoration.
5. Compare the archived and candidate ROMs over identical frozen scenes:
   adaptive descriptors/depth/segments, physical columns, generated BG tiles,
   complete maps/attributes, object patterns/OAM, HUD packets and final RGB.
   Retain per-step timing results. Never replace an accepted pixel fixture to
   make an optimization pass.
6. Execute the full regression suite, live diagnostics, controller-only level
   completion, alternate rendering modes and maintained independent emulators.
   Live routes measure responsiveness under fixed ticks; their changing actor
   poses are not an exact-input A/B benchmark.
7. Record the candidate hash, measured gains and memory costs. Build a separately
   named downloadable candidate, preserving prior ROMs and source archives.

## Why continuation is exact

The existing certificate proves each accepted coarse crossing has the same
order as the Q14 traversal: `abs(error) > nextX + nextY`, with every generated
component differing by strictly less than one coarse unit. Thus the current
cell, the next two boundary distances and the count are identical immediately
before the first uncertain crossing. For nonzero coarse components, the same
bound also proves sign agreement. Reinitializing the fine error at that point
is sufficient; retracing the earlier cells adds no information.

A zero coarse component uses a sentinel boundary distance, so that case still
restarts. A cast whose origin lies inside a door cell also retains its local
panel test. Continuations have already tested their current cell, including
any finite panel, and do not test it a second time. The certificate threshold,
Q14 vectors, Q5 projection and adaptive reconstruction rules are unchanged.

## Reproduce the exact-output comparison

Keep the accepted ROM and its matching `.sym` file outside the build outputs
before building a candidate, then run:

```sh
python3 tools/benchmark_runtime.py \
  --baseline-rom /path/to/accepted/lupine3d.gb \
  --baseline-symbols /path/to/accepted/lupine3d.sym \
  --output build/runtime_comparison.json
python3 tools/profile_rendering.py --output build/profile_runtime.json
```

The frozen corpus includes authored art/coherence poses and both approaches to
every door at five opening fractions. It suspends simulation using explicit
diagnostic RAM injection while leaving LCD interrupts and publication active.
Every frame also passes the host geometry/compositor validation. Arithmetic
tests independently check quotient, remainder, overflow and table-bank edges;
an open-room ray corpus compares continuations to full Q14 restarts, including
late ambiguous crossings.

## Accepted measurements

Candidate **0.7.0-beta.3**, SHA-256:
`0890469007ab8d470d15c07d95a319c9565b27df8d40ca0511572aefe41754a3`.

| Project-harness measurement | Accepted Sable baseline | Candidate |
|---|---:|---:|
| Frozen scenes, mean update cycles | 1,335,498.642 | 1,218,899.623 |
| Frozen scenes, mean casting cycles | 932,082.113 | 833,677.208 |
| Coherence route, mean cycles | 1,006,437.091 | 980,901.818 |
| Live combat route, mean cycles | 1,287,407.319 | 1,218,677.191 |
| Live combat route, maximum cycles | 2,105,892 | 1,685,836 |
| Live combat route, minimum visual updates/s | 3.9834 | 4.9759 |

All **53/53 frozen scenes** preserve all six output groups and ray counts.
This is an **8.73% mean update-cost reduction** and a **10.56% casting-cost
reduction**. Live combat mean cost falls 5.34%, with its recorded maximum down
19.95%; those live figures also reflect changed simulation sampling and VBlank
phase. The nine existing reviewed RGB fixtures remain untouched. No new colour,
texture or reconstruction approximation is introduced.

The fully unrolled prototype was faster but left only 2,355 resident bytes,
failing the existing 3,000-byte reserve gate. Four-bit groups retain most of the
division savings. Relocating the unaligned startup map after the hot tables
avoids a 1 KiB alignment jump. The accepted image retains **3,123 free resident
bytes**, uses the same 4 MiB cartridge and allocates no new HRAM or VRAM. The
group counter adds two temporary stack bytes inside the existing reserve.

The final candidate passes 75 automated tests, the controller-only level
completion (236 verified updates, 84 health), rendering variants, and SameBoy
CGB-0/CGB-E plus mGBA controller/startup lanes. The independent lanes observe
62 page swaps in 480 LCD frames; SameBoy observes no unsafe DMA starts/flips.
Detailed hashes and timings are in
[`research/results/runtime_beta3.json`](../research/results/runtime_beta3.json).

Physical CGB/flash-cartridge acceptance remains a separate, pending gate.
