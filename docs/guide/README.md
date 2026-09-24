# Developer guide

Lupine 3D is a first-person engine for the Game Boy Color: Python emits SM83
machine code, tables, levels and art into a deterministic 4 MiB MBC5 ROM, and
a host harness plus two pinned emulator cores prove every frame. This guide
is for building a first-person game on it, or changing the engine itself.

| Page | Read it when |
|---|---|
| [Hardware primer](HARDWARE.md) | you want to know what the console gives the engine and which rules the engine treats as invariants |
| [Engine tour](ENGINE_TOUR.md) | you want the path from a button press to a published VRAM page, with the module that owns each step |
| [Memory map](MEMORY_MAP.md) | you need an address: generated from the machine-checked allocation ledger of the current build |
| [How-tos](HOWTO.md) | you are adding a level, an enemy kind, a weapon, a texture, a screen or a check |
| [Debugging](DEBUGGING.md) | something is wrong and you want to look inside the ROM in the harness, a debugger or a core |

## Five-minute start

```sh
python3 tools/dev_setup.py && source .venv/bin/activate
make build test                                   # the ROM, its exports and the regression suite
python tools/lupine.py level check games/sable_outpost/levels/*.json  # every level's certificate
python tools/lupine.py run                        # the coherence tour, every frame checked
python tools/lupine.py symbols                    # where the debugger exports are
```

`build/lupine3d.gb` runs in any CGB-capable emulator; SameBoy and mGBA are
the pinned ones. There is no cartridge RAM: progress is a four-digit
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
[architecture](../ARCHITECTURE.md) page states these contracts precisely and
[verification](../VERIFICATION.md) says how each one is checked.

## Content reference

- [Level format](../LEVEL_FORMAT.md) and [certificate](../LEVEL_CERTIFICATE.md)
- [Art pipeline](../ART_PIPELINE.md)
- [Textured walls](../TEXTURED_WALLS.md), the slim default
- [Development](../DEVELOPMENT.md): commands, cores, releases
