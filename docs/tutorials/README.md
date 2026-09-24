# Developer guide

Lupine 3D is a first-person engine for the Game Boy Color: Python emits SM83
machine code, tables, levels and art into a deterministic 4 MiB MBC5 ROM, and
a host harness plus two pinned emulator cores prove every frame. This guide
is for building a first-person game on it, or changing the engine itself.

| Page | Read it when |
|---|---|
| [Hardware primer](../explanation/hardware.md) | you want to know what the console gives the engine and which rules the engine treats as invariants |
| [Engine tour](../explanation/engine-tour.md) | you want the path from a button press to a published VRAM page, with the module that owns each step |
| [Memory map](../reference/memory-map.md) | you need an address: generated from the machine-checked allocation ledger of the current build |
| [How-tos](../how-to/README.md) | you are adding a level, an enemy kind, a weapon, a texture, a screen or a check |
| [Debugging](../how-to/debug-a-build.md) | something is wrong and you want to look inside the ROM in the harness, a debugger or a core |

## Five-minute start

```sh
python3 tools/dev_setup.py && source .venv/bin/activate
make build test                                   # the ROM, its exports and the regression suite
python tools/lupine.py game check                # the game's manifest and every level's certificate
python tools/lupine.py run                        # the coherence tour, every frame checked
python tools/lupine.py symbols                    # where the debugger exports are
```

`build/lupine3d.gb` runs in any CGB-capable emulator; SameBoy and mGBA are
the pinned ones. That is the showcase, `games/sable_outpost`; every command
takes `--game DIR` for another game (`make … GAME=DIR`), which builds into
`build/games/<id>/`, and `python tools/lupine.py new-game DIR --from GAME`
starts one as a copy. There is no cartridge RAM: progress is a four-digit
continue code shown after each sector.

## The contracts in one paragraph

Simulation runs at cooperative yields in WRAM bank 2 on a fixed tick and
renders from an immutable snapshot in bank 1. A frame is cast with forty-one
prepared rays and reconstructed to 160 columns, composed into a ring of
dynamic patterns, and published to the hidden VRAM page by HBlank DMA during
composition plus one VBlank tail. Everything the console draws is predicted
byte for byte by a Python model, and every invariant (geometry, publication
safety, the MBC5 bank rule, the resident reserve, core agreement) is a hard
gate; pictures are golden snapshots with an explicit acceptance path. The
[architecture](../explanation/architecture.md) page states these contracts precisely and
[verification](../explanation/verification.md) says how each one is checked.

## Content reference

- [Level format](../reference/level-format.md) and [certificate](../reference/level-certificate.md)
- [Art pipeline](../reference/asset-formats.md)
- [Textured walls](../explanation/textured-walls.md), the slim default
- [Development](../engine/development.md): commands, cores, releases
