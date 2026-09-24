# Verification: hard gates and snapshots

Lupine 3D proves two different things about every build, and keeps them
apart. **Hard gates** are properties of the engine that no art change can
legitimately alter; a failure is a bug and is never accepted. **Snapshots**
are what frames looked like; a difference is reviewed as an image and either
accepted with a note or fixed. Hash oracles used to conflate the two, so a
deliberate pixel change and a broken compositor failed the same way. They no
longer gate anything (the files are retained under `playtests/archive/oracles/`).

## Hard gates

| Property | Where it is enforced |
| --- | --- |
| Geometry and compositor model equality: every ray/pixel descriptor, dynamic tile byte, map byte and attribute byte the ROM produces equals the Python reference model | `validate_frame` in `tools/playtest.py`, run on every frame of the driven routes, the controller route, the variants and the wall-reuse scenes |
| Publication safety: no CPU write to the visible map, no GDMA start outside VBlank, HBlank streaming only from fixed WRAM with the transfer idle at the flip, bounded block counts | `tools/sm83emu.py`, `tools/check_sable.py`, `tools/release_check.py` |
| MBC5 bank contract over the emitted image | `tools/lupine3d_v4/bank_safety.py` and `tests/test_bank_safety.py` |
| Memory: 3,000 resident bytes free, the 512-byte stack, allocation and lifetime assertions | `tools/lupine3d_v4/allocation.py`, `layout.py` |
| Exact A/B equality: folded vs unfolded, wall reuse on vs off, prepared rays on vs off, cached vs full over 53 frozen scenes | `make variants`, `tools/benchmark_wall_reuse.py` |
| Independent cores: pinned SameBoy CGB-0/CGB-E and mGBA produce byte-identical RGB to the host over the frozen witness scenes and the 480-frame script | `tools/independent_witnesses.py`, `tools/sameboy_verify.py`, `tools/mgba_verify.py` |
| The frozen v1 ROM hash and deterministic rebuilds; the legacy profile byte-identical to its previous sources | `tests/test_engine.py`, `tools/check_display.py` |
| Level compiler certificates for every campaign level | `tools/lupine3d_v4/levels.py`, `tools/release_check.py` |
| Controller-only completion of every sector with zero game-RAM writes (`--sectors A-B` plays a range, entering a later start by typing its continue code on the title; the failure report lists every combat exchange) | `tools/playthrough.py` |

Never weaken one of these to pass. If a gate and the ROM disagree, one of
them has a bug; find which.

## Snapshots

`tools/snapshot.py` keeps one golden PNG per scene under
`snapshots/<profile>/<suite>/` with a `manifest.json` that records, per scene,
the RGB SHA-256, the ROM SHA-256 and configuration it was accepted on, who
accepted it, when, and **why**. The profile is the display/art pair, with
`-textured` for textured walls (`slim-sable-v2-textured` for the production
build).

| Suite | Producer | Scenes |
| --- | --- | --- |
| `tour` | `make playtest` (`playtests/sable_v10_coherence_tour.json`) | 9 |
| `world` | `make playtest-world` | 14 |
| `art` | `make playtest-art` | 6 |
| `sable` | `tools/check_sable.py` (six diagnostic poses) | 6 |
| `witnesses` | `tools/independent_witnesses.py` (host images of the frozen scenes) | 87 |
| `route` | `tools/playthrough.py` captures, **recorded, not checked**: where a capture lands depends on the steering script | ~25 |

Every producer runs in `check` mode by default: a scene that changed, is new
or is missing fails the producer and names the scene. The evidence is always
written to `build/snapshots/<profile>/<suite>/`: `actual/`, `expected/`,
`diff/` (changed pixels in red over the dimmed actual), `report.json`
(status, changed-pixel count, bounding box, world/HUD split) and a single-file
`report.html` with the three images side by side. CI uploads that directory
as the `visual-diff-<sha>` artifact.

### Reviewing and accepting a change

```sh
make playtest                      # fails: "snapshot suite 'tour' differs from its goldens: 09_exit_approach (changed, 6 px)"
python tools/snapshot.py diff --suite tour
open build/snapshots/slim-sable-v2-textured/tour/report.html
python tools/snapshot.py accept --suite tour --scene 09_exit_approach \
    --note "streamed publication presents one interval earlier; helmet blink phase moves"
git add snapshots/ && git commit
```

`accept` refuses an empty note, refuses scenes the last run did not produce,
and retires a golden whose scene is `missing`. Accept only what you can
explain in the note; the PR shows the PNG diff. Nothing in CI accepts.

`--snapshot-mode record` writes the same evidence without failing (used for
the route, and for exploring a change before accepting it);
`--snapshot-mode none` skips snapshots (for a foreign ROM such as an archived
baseline).

### What a snapshot does not prove

A matching snapshot says the frame is the frame it was. It does not say the
frame is right: that is the reference model's job, and it runs on the same
frame. A changed snapshot with every hard gate green is a visual decision,
not a defect.

## Lanes

- `make test` — the regression suite (historical tests under the legacy
  profile, then fresh-process production checks).
- `make playtest playtest-world playtest-art` — the driven routes with
  snapshot checks (CI `fast` job, with the visual-diff artifact).
- `make variants wall-reuse motion`, `make sameboy`, `make mgba`,
  `python tools/independent_witnesses.py` — exact A/B equality, timed motion
  and the pinned cores (CI `slow` job).
- `make playthrough SECTORS=A-B` — the controller route, one chunk of
  `tools/ci_lanes.py` per CI `route` job; `make playtest-sync` — the
  synchronous publication tail (CI `profiles` job).
- `make identity` (`tools/rom_identity.py`) — every configuration the project
  builds (default, sync, compact, legacy, the A/B variants, the level
  fixtures) byte-identical to a recorded ROM, or to a git ref with
  `compare --base`; the gate of refactors meant to change no behaviour (CI
  `identity` job while the game/engine separation is under way).
- `python tools/ci_local.py` — all of CI's lanes locally, in parallel, each
  in its own copy of the working tree; `--changed` picks the lanes a change
  needs, `--list` prints them.
- `tools/sable_sustained.py` — the eight sixty-second trials (manual and
  release qualification, never short CI).
- `python tools/release_check.py` — the aggregate gate over all of the above.

## Overlapped publication

On the slim default a packet is published by the VBlank interrupt after the
main loop has already taken the next render snapshot, so the live WRAM no
longer describes the frame on screen. The harness (`tools/sm83emu.py`)
therefore captures WRAM and HRAM when the main loop reaches
`publication_handoff`:

* **Right after a presentation** the machine shows that capture to the host
  until the CPU steps again or the host writes: a producer that runs to a
  presentation and then reads state (a validator, an OAM budget, a wall key)
  reads the state the presented packet was built from. VRAM, OAM, palettes,
  I/O and the variables the tail itself writes (the pages, the presentation
  serial) stay live. A packet published synchronously (a reused wall view)
  has no hand-off and is read live, as before. `presented_view()` gives the
  same view later.
* **A host write to a running machine** belongs between frames:
  `set_test_world_byte` and `apply_diagnostic_camera` first call
  `diagnostic_barrier()`, which runs to the top of `main_loop`, where the
  packet in flight is fully composed and the next snapshot not yet taken.
  Tools that write RAM directly (the witness setup, the wall-reuse
  benchmark, the door action of the folding variant, the motion replay's
  clock reset) call it themselves. Packets handed off before a barrier are
  stale: still published, still checked for publication safety and recorded
  in `stale_commit_events`, but not the presentation the diagnostic waits
  for.
* **A producer that freezes the machine with interrupts off** still gets its
  frames: `wait_tail` publishes a pending packet itself at the next VBlank's
  entry, the same point the interrupt would have.

On a ROM without the hand-off (the legacy and compact profiles, and
`LUPINE3D_OVERLAP_PUBLICATION=0`) every one of these is a no-op. The
wall-reuse benchmark compares the masked OBJ page as a page, like the BG
page: publication parity differs between a cached and a full machine.

## The host harness and hardware conformance

`tools/sm83emu.py` is a deterministic model, not a cycle-accurate emulator:
it executes the closed set of opcodes the emitter uses, models GDMA and
HBlank DMA carefully, and rasterises frames from VRAM/OAM/palette state. It
has no STAT mode timing, no timers and no sound, so the public conformance
suites (mooneye, cgb-acid2, mealybug) cannot run on it and are not claimed.
What holds it honest is differential:

- **CPU conformance** (`make conformance SAMEBOY_DIR=…`,
  `tools/harness_conformance.py`): seeded micro-programs built from every
  instruction form `tools/sm83.py` can emit (loads, the eight ALU operations
  against registers, immediates and `(hl)`, all CB rotates/shifts/bit ops,
  16-bit arithmetic, `ldi`/`ldd`, HRAM and absolute addressing, push/pop
  including `pop af`'s flag mask, conditional `jr`/`jp`/`call`/`ret`,
  `reti`, `jp (hl)`, `ld sp,hl`, `ld (nn),sp`) run in the harness and in
  SameBoy (`tools/sameboy_dump.c`), and A F B C D E H L SP plus a 512-byte
  scratch window must agree byte for byte. Sixty-four programs of 240 forms
  each per run; a mismatch is a harness defect. Timing and I/O are out of
  scope by construction (interrupts off, no register reads).
- **PPU agreement**: exact RGB equality with the two pinned cores across the
  witness corpus and the reference models above. SameBoy's adapter also
  counts CPU writes to VRAM and to the palette data ports while the PPU is
  in mode 3 (`mode3_vram_writes`, `mode3_palette_writes`), which the harness
  cannot see; both must be zero.

Anything no emulator sees stays in `HARDWARE_TEST_CHECKLIST.md` as untested.
