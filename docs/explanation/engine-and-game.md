# The engine and the game

Lupine 3D is an engine; a game is data it builds. This page draws the line
between them: what the engine decides, what a game decides, and what a game
cannot change yet.

## From files to a cartridge

```text
games/<id>/                         tools/ (the engine, Python)                  build/games/<id>/
  game.json ─────────┐
  levels/*.json      │   game.py        load and check the game (limits.py)
  textures/*.png     ├─► levels.py      compile and certify each level        ─►  lupine3d.gb   (4 MiB MBC5 ROM)
  art/sprites.json   │   palettes.py    themes → CGB palette sets                  lupine3d.sym  (debugger symbols)
  art/native/*.png   │   texture_*.py   textures → row-window blocks               lupine3d.map, .lst
  screens.json       │   screens.py     text → patterns and maps                   build_manifest.json
  audio/*.json      ─┘   music.py       songs → sequencer rows
                          emitter, …    SM83 code, tables, the linker (build_rom.py)
                                             │
                          sm83emu.py ◄───────┘ every frame checked against the host model
```

A build reads one game (`LUPINE3D_GAME`, `--game`), compiles its content,
emits the engine's SM83 code around it, and links one deterministic ROM: the
same sources always give the same bytes. The build never runs code from a
game directory and never generates an image.

## What the engine decides

- **The renderer.** A first-person view of a 16×16 grid world, 160×120
  pixels over a 24-pixel HUD, cast with 41 prepared rays and reconstructed to
  160 columns, textured walls with depth shading, doors that slide, enemies
  drawn as masked sprites at up to four distances. The frame has no framebuffer:
  it is composed into Game Boy Color tiles and published by DMA.
- **The simulation.** A fixed tick: movement and collision, doors, the
  enemies' waking, patrolling, chasing and contact, hitscan shots,
  drops, the exit.
- **The console's budgets.** VRAM patterns, OBJ palettes and objects per
  scanline, ROM banks, WRAM and the resident code's bank-0 space: the
  [limits](../reference/limits.md) a game meets are these, stated as content.
- **The controls, the HUD's layout, the screens' frame and font.**
- **The proof.** Every published frame is checked against a Python model of
  what it must be; bank safety, memory and publication safety are proven on
  the emitted image.

## What a game decides

Everything in its directory ([game manifest](../reference/game-manifest.md)):
the levels and their order in episodes; the enemy kinds' stats, drops and
colours; the four weapons' numbers, sheets and unlocks; the themes' textures
and colours; every sprite sheet and the HUD chassis; the screens' text; the
songs and sound effects; the HUD's words; the cartridge header.

## What a game cannot change yet

These are engine properties today. Each could become content; none is a
setting a game can reach.

| Fixed | Because |
|---|---|
| 16×16 levels, up to 6 doors, 6 enemies, 16 fixtures | the level slot and the door and actor records ([level format](../reference/level-format.md)) |
| every enemy kind uses one set of twelve frames | the cel dictionaries are built for one actor sheet at three or four distances |
| one resident wall atlas profile for the whole game | levels must agree on `vram_profile`; switching would need atlas streaming |
| the enemy behaviour | patrol, chase and contact are engine code; a kind sets only speed, damage, recovery and drop |
| one activation radius a level | the level header carries the first enemy's |
| the HUD's fields and their places | the HUD packet's layout is the engine's ABI; a chassis must leave room for them |
| three episodes | each episode's screen dispatch is resident code in bank 0 |
| the controls and the skill rules | engine code |

## The showcase and the starter

**Sable Outpost** (`games/sable_outpost`) is the showcase: eighteen levels in
three episodes, four enemy kinds, three themes, seven textures, and art made
for it. The engine's own evidence (the regression suite, the pinned cores,
the performance measurements) is recorded on it, and it is the only game that
builds the engine's historical display profiles.

**The starter** (`games/starter`) is the smallest complete game, made to be
copied: two levels, two kinds, one theme. CI builds it, tours it against its
goldens, plays it to its ending and restarts it, so a new game made from it
starts from a known-good place.
