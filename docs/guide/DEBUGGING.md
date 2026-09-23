# Debugging a build

## Symbols and the map

Every build writes `build/lupine3d.sym` in the RGBDS `BB:AAAA name` form
that BGB, Emulicious and SameBoy's debugger read, and `build/lupine3d.map`
with the assembler's sections and the allocation ledger. `python
tools/lupine.py symbols` prints where they are and how to load them. RAM
variables are exported with their WRAM bank, so a watch on `PLAYER_X` or
`GAME_MODE` works by name; switchable-bank names carry the bank the layout
gives them (`WRAM_BANK_OF_NAME`).

## The host harness

`tools/sm83emu.py` runs the ROM on the host with exact instruction timing, a
DMA model and per-frame validation. It is what every driven scenario, tour
and check uses, so a bug that shows in an emulator can usually be reduced to
a harness script:

```sh
python tools/lupine.py run --scenario playtests/sable_v10_coherence_tour.json
python tools/lupine.py profile           # T-cycles by main-loop stage on the tour
```

`validate_frame` in `tools/playtest.py` refuses a frame whose descriptors,
patterns, maps, masks or DMA timing disagree with the host model, naming the
check. Its captures land under `build/playtest/<scenario>/` with a contact
sheet and a report.

## Reproducing a core failure

The pinned SameBoy and mGBA adapters (`tools/sameboy_smoke.c`,
`tools/mgba_smoke.c`) compare every frame with the host rasteriser. SameBoy
randomises power-on RAM from the clock, so a failure can depend on the seed:

```sh
LUPINE3D_SAMEBOY_SEED=12345 make sameboy SAMEBOY_DIR=build/deps/SameBoy
LUPINE3D_DUMP_RAM=build/ram.bin make sameboy SAMEBOY_DIR=build/deps/SameBoy
```

The dump can be loaded into the harness to replay the same power-on state
(`docs/DEVELOPMENT.md`, "Power-on RAM in the core adapters"). Both adapters
press START first and wait for the ROM's own write of `MODE_PLAYING`.

## Snapshots and pictures

A visual difference is a golden-image diff: `python tools/snapshot.py diff
--suite tour` writes `build/snapshots/tour/report.html` with expected, actual
and the changed pixels. Accepting a change is explicit and noted
(`docs/VERIFICATION.md`). `make preview` renders actual emulator images.

## Common failures

| Symptom | Where to look |
|---|---|
| Build refuses: resident reserve below 3,000 or fixed half full | `build/lupine3d.map` sections; move bank-neutral code to `cold_sections` in `build_rom.py` |
| `bank_safety` rejects the image | a bank-register write above `$4000`, a section falling through, or a conditional bank restore |
| Frame refused for DMA timing | a transfer started with `HDMA5` busy, a VBK write during a transfer, or a VBlank tail past line 153 |
| Harness and SameBoy disagree | run `make conformance` for the CPU model, then the witness scenes for the PPU |
| A level is refused | `python tools/lupine.py level check` prints the compiler's reason (`docs/LEVEL_CERTIFICATE.md`) |
| Art refused at build | `sprite_assets.frames`: mode, size, transparency index, palette or SHA-256 mismatch with `assets.json` |
