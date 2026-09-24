# Engine development

This part of the handbook is for changing Lupine 3D itself: the SM83 code it
emits, its tables, its tools and its checks. Making a game needs none of
it; start at the [handbook](../README.md) for that.

## Where things are

The engine is Python that emits a ROM. `tools/build_rom.py` is the linker and
the compatibility facade; the modules under `tools/lupine3d_v4/` own one area
each ([AGENTS.md](../../AGENTS.md) has the full code map):

| Area | Modules |
|---|---|
| A game's data | `game.py` (the loader), `limits.py`, `palettes.py`, `fonts.py` |
| Layout, flags, allocation | `layout.py`, `configuration.py`, `allocation.py`, `bank_safety.py` |
| Rays, projection, walls | `precision.py`, `ray_setup.py`, `columns.py`, `textured.py`, `texture_reference.py` |
| Simulation and the living world | `simulation.py`, `living_world.py`, `actors.py`, `door_geometry.py` |
| Levels | `levels.py`, `surfaces.py`, `world_decor.py`, `tmx_import.py` |
| Screens, music, art | `screens.py`, `music.py`, `artwork.py`, `sprite_assets.py`, `animation.py` |
| Assembler and harness | `tools/sm83.py`, `tools/sm83emu.py` |

**The build never imports from `games/`.** A game is data the loader reads;
an offline tool a game ships (the showcase's weapon renderer) makes PNGs
that are committed, never run by a build.

## The rules a change keeps

Engine invariants are hard gates, never snapshots, and a check is never
weakened to pass:

- Every frame the ROM publishes equals the host model's: geometry
  (`reference.py`), walls (`texture_reference.py`), publication safety
  (`playtest.validate_frame`).
- The MBC5 bank contract (`bank_safety.py`): bank switches and everything an
  interrupt reaches stay in bank 0, nothing runs above `$4000` with a foreign
  bank mapped, no section falls through into another.
- Memory: the allocation ledger's ranges never overlap, the 3,000-byte
  resident reserve and the 512-byte stack hold.
- The pinned cores agree with the harness (SameBoy CGB-0 and CGB-E, mGBA),
  and the harness's CPU agrees with SameBoy on every emitted instruction form
  (`make conformance`).
- The frozen v1 ROM hash and the legacy profile are contracts.

[Verification](../explanation/verification.md) says how each is checked.

## A refactor changes no byte

When a change should not change behaviour, prove it:

```sh
python tools/rom_identity.py compare --base origin/main
```

builds ten configurations (the showcase's default, sync, compact, legacy,
the diagnostics and the engine's fixture levels) from your tree and from the
base, each in a fresh process, and compares every ROM byte for byte.

## Pages

| Page | For |
|---|---|
| [Development](development.md) | setup, the pinned emulator cores, diagnostics and releases |
| [Your first engine change](../tutorials/first-engine-change.md) | a guided change, end to end |
| [Add a routine](add-a-routine.md) | emitting new SM83 code: placement, clobbers, the host model |
| [Add a check](add-a-check.md) | a new hard gate or golden scene |
| [Add a screen mode](add-a-screen-mode.md) | a new full-screen mode |
| [The assembler](assembler.md) | `tools/sm83.py`: the emitter API and adding an instruction form |
| [The harness](harness.md) | `tools/sm83emu.py`: running, poking and checking a ROM from Python |
| [Hardware checklist](hardware-checklist.md) | what a first run on real hardware would need to show |

Before you push: `python tools/lupine.py ci` runs every CI lane locally, each
in its own copy of the tree.
