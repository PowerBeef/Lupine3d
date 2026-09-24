# How-tos

Each recipe names the files to touch, the limits that apply and the checks
that prove the change. Run the checks from the repository root in the
virtual environment; `make test` is the floor for anything that changes the
ROM.

## Add a campaign level

1. Copy a sector under `games/sable_outpost/levels/` (or export one to
   Tiled: `python tools/lupine.py level export-tmx
   games/sable_outpost/levels/vent_stacks.json build/vent.tmx
   --swatch`, edit, then `lupine level import-tmx`). The format, units and
   limits are in `docs/LEVEL_FORMAT.md`.
2. `python tools/lupine.py level check games/sable_outpost/levels/new.json` until the
   certificate passes (`docs/LEVEL_CERTIFICATE.md`). Fix the level, never
   the limits.
3. Add the file to an episode's `levels` in `games/sable_outpost/game.json`.
   Levels are packed five to a ROM bank from 241 (a resident directory gives
   the loader each one's bank and slot page), and every campaign level must
   share the first level's `vram_profile`; `palette_profile` names the
   episode's palette set and may differ per level.
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
   There are four records because the kind byte is masked to two bits, and
   all four are used (the fourth is the boss), so a fifth kind needs a wider
   kind mask, not another record.
3. The palette: all eight OBJ palettes are allocated (`docs/ART_PIPELINE.md`).
   A distinct look means re-planning owners, not adding a slot; run `python
   tools/palette_plan.py` and change `obj_palette_values` deliberately.
4. Field it in a level's `entities`. `make test playtest-world playthrough`;
   `python tools/check_sable.py` for the cel and palette contracts.

## Add a weapon

Four weapons share one eighty-pattern window at `$8200` in VRAM bank 1; SELECT
walks to the next owned one with the LCD off. The count is a power of two
(the index is masked), so a fifth weapon means eight slots.

1. Art: a model function in `games/sable_outpost/art/tools/render_weapons.py` (parts with a
   material and a name, the moving ones marked `action`), added to `MODELS`
   and `WEAPONS`, rendered into `games/sable_outpost/art/native/` with
   `python games/sable_outpost/art/tools/render_weapons.py --write` (`docs/ART_PIPELINE.md`,
   "Weapons are rendered from models"). It compiles to exactly
   `WEAPON_TILE_BYTES` in the 8×16 pair order, and its manifest record
   carries the fitted `object_palettes`.
2. `weapon_stats` in `build_rom.py`: damage and recovery ticks. The shotgun's
   record is the engine's original behaviour and every measurement's
   baseline, so change the new record only.
3. `WEAPON_COUNT`, `WEAPON_SHEET_LABELS` and `WEAPON_UNLOCK_SECTORS` in
   `layout.py`, the sheet maker in `make_weapon_assets` (`build_rom.py`, the
   sheets share `WEAPON_ROM_BANK`) and the manifest entry in
   `games/sable_outpost/art/sprites.json`. The swap itself is weapon-agnostic: one GDMA
   of the cel sheet, from the main loop, with the LCD off.
4. `make test playtest-art`, `python tools/check_sable.py`, both cores
   (`make sameboy mgba`) because the swap is an LCD-off VRAM upload, and
   accept the new goldens with a note.

## Add a wall texture

1. Author a 16×8 indexed PNG (the upper half of a 16×16 face; the compiler
   mirrors it) using indices 1..3 only, under your game's `textures/`.
2. Name it in `game.json` `textures` and give it a role (structure,
   machinery or door) in a theme's `textures`: a theme is the (structure,
   machinery, door) textures and the colours of one palette set, so a
   level gets it through its `palette_profile`, and a level chooses per-face
   profiles with `surfaces`. Each texture is four 5 KiB shade
   blocks, three blocks to a bank, in the order `TEXTURE_WINDOW_BANKS`
   gives; the build refuses more blocks than those banks hold.
3. `make build playtest playtest-world playtest-art sable-check` (textured
   walls are the only slim renderer); the reference in `texture_reference.py`
   predicts every tile byte, so a mismatch is a bug in one of them, never
   something to accept. Accept the changed goldens with a note.

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

Engine invariants are hard gates: put them in `tests/` (a test that needs the
slim configuration spawns a fresh process, as `tests/test_textured_walls.py`
does), `tools/check_sable.py`
or `tools/release_check.py`. Visual expectations are golden snapshots: add a
scene to a suite and accept it with a note. A check is never weakened to
pass; the archived hash oracles show what that policy replaced.
