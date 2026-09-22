# How-tos

Each recipe names the files to touch, the limits that apply and the checks
that prove the change. Run the checks from the repository root in the
virtual environment; `make test` is the floor for anything that changes the
ROM.

## Add a campaign level

1. Copy a sector under `levels/` (or export one to Tiled: `python
   tools/lupine.py level export-tmx levels/vent_stacks.json build/vent.tmx
   --swatch`, edit, then `lupine level import-tmx`). The format, units and
   limits are in `docs/LEVEL_FORMAT.md`.
2. `python tools/lupine.py level check levels/new.json` until the
   certificate passes (`docs/LEVEL_CERTIFICATE.md`). Fix the level, never
   the limits.
3. Add the file name to `CAMPAIGN_ORDER` in `tools/lupine3d_v4/levels.py`.
   Levels are packed five to a ROM bank from 241 (a resident directory gives
   the loader each one's bank and slot page), and every campaign level must
   share the first level's `vram_profile` and `palette_profile`.
4. `make build test playthrough`: the controller route plays every sector
   with input only, so it must be able to clear yours. `make variants` if you
   changed a level the variants use.
5. New views mean new golden scenes only if you add them to a tour;
   otherwise the snapshot suites are unaffected.

## Add an enemy kind

Kinds share the Sentinel's cels; a kind is stats plus an OBJ palette.

1. `ENTITY_KIND_IDS` and `KIND_DROPS` in `levels.py`: the ID is the stat
   table index, and the drop must be a kind in `DROP_KIND_IDS`.
2. `actor_kind_stats` in `tools/build_rom.py`: eight bytes (contact damage,
   attack recovery in AI ticks, Q8 step, OBJ palette, drop, three spare).
   There are four records because the kind byte is masked to two bits, so a
   fourth kind replaces the spare that repeats the Sentinel.
3. The palette: all eight OBJ palettes are allocated (`docs/ART_PIPELINE.md`).
   A distinct look means re-planning owners, not adding a slot; run `python
   tools/palette_plan.py` and change `obj_palette_values` deliberately.
4. Field it in a level's `entities`. `make test playtest-world playthrough`;
   `python tools/check_sable.py` for the cel and palette contracts.

## Add a weapon

Two weapons share one eighty-pattern window at `$8200` in VRAM bank 1; SELECT
swaps them with the LCD off.

1. Art: a native 32×32 five-cel indexed PNG (`assets/sable_v2/`) or an
   authored pixel table like `make_slug_tiles` in `resources.py`. It must
   compile to exactly `WEAPON_TILE_BYTES` in the 8×16 pair order.
2. `weapon_stats` in `build_rom.py`: damage and recovery ticks. The shotgun's
   record is the engine's original behaviour and every measurement's
   baseline, so change the new record only.
3. `WEAPON_COUNT` in `layout.py` and the tile source selection next to
   `service_weapon_swap` in `emitter.py` (the swap is one GDMA of the cel
   sheet, from the main loop, with the LCD off).
4. `make test playtest-art`, `python tools/check_sable.py`, both cores
   (`make sameboy mgba`) because the swap is an LCD-off VRAM upload, and
   accept the new goldens with a note.

## Add a wall texture

1. Author a 16×8 indexed PNG (the upper half of a 16×16 face; the compiler
   mirrors it) using indices 1..3 only, under `assets/textures/`.
2. Add its name to `TEXTURE_NAMES` in `texture_assets.py`. The index is what
   a surface profile selects; three textures use banks 248-251 at four 5 KiB
   shade blocks each. A level chooses per-face profiles with `surfaces`.
3. `make textured playtest-textured sable-check-textured`; the reference in
   `texture_reference.py` predicts every tile byte, so a mismatch is a bug in
   one of them, never something to accept. Accept the textured goldens with a
   note.

## Add a full-screen mode

1. Add a screen to `SCREEN_SOURCES` in `screens.py`: lines of `(text, y,
   colour, scale)` or `(label, y, colour, scale, digits)` for cells the
   runtime rewrites. `compose_screen` places the cells on tile boundaries,
   refuses a line that straddles a tile row and refuses more than
   `SCREEN_PATTERN_CAPACITY` patterns or `SCREEN_SLOT_CAPACITY` slots. Never
   place runtime cells by hand.
2. Give it a mode in `emit_screens`: a full-screen mode owns the whole
   background with LCDC `$81`, writes with the LCD off, ticks the sequencer
   from its loop and reads the pad itself. Runtime digits (patterns 0-9,
   blank 10) go into reserved cells before the LCD comes back on.
3. Drive it in a scenario and add the frame to a snapshot suite; `make test
   playtest` and both cores if the mode moves data with the LCD off.

## Add an engine routine

1. Emit it in the module that owns the area (`AGENTS.md`, "Code map") and
   document register and flag clobbers, stack use and bank ownership.
2. Placement is a build decision: bank-register writes and anything an
   interrupt reaches stay below `$4000`; bank-neutral code goes in
   `cold_sections`. The linker refuses a build that breaks the 3,000-byte
   resident reserve, and `bank_safety.py` refuses one that breaks the MBC5
   rule.
3. A new opcode form needs `tools/sm83.py`, `tools/sm83emu.py` and a run of
   `make conformance` against SameBoy.
4. If it changes output, the host model changes with it in the same commit:
   `reference.py`, `texture_reference.py` or the module's own model. Then
   `make test playtest playtest-world` and the checks the affected area lists
   in `AGENTS.md`, "Verification and evidence".

## Add a check

Engine invariants are hard gates: put them in `tests/` (fresh-process lanes
in `tools/run_tests.py` for the slim configuration), `tools/check_sable.py`
or `tools/release_check.py`. Visual expectations are golden snapshots: add a
scene to a suite and accept it with a note. A check is never weakened to
pass; the archived hash oracles show what that policy replaced.
