# The Lupine 3D handbook

Lupine 3D is a first-person 3D engine for the Game Boy Color. A game is a
folder of data (levels, art, music, text); the engine, written in Python,
builds it into a cartridge ROM and proves every frame it draws. This
handbook teaches you to make games with it, and to change the engine.

New here? Start with **[your first game](tutorials/first-game.md)**: thirty
minutes from nothing to your own game playing in an emulator.

## Tutorials: learn by doing

- [Your first game](tutorials/first-game.md): the starter, copied, changed, checked and played.
- [Your first level](tutorials/first-level.md): a level from a blank grid to the campaign.
- [Your first engine change](tutorials/first-engine-change.md): for contributors to the engine.

## How-to guides: get a job done

| Levels and progression | Look and sound | Testing and shipping |
|---|---|---|
| [Add a level](how-to/add-a-level.md) | [Themes and palettes](how-to/themes-and-palettes.md) | [Test your game](how-to/test-your-game.md) |
| [Use Tiled](how-to/use-tiled.md) | [Wall textures](how-to/wall-textures.md) | [Debug a build](how-to/debug-a-build.md) |
| [Episodes and progression](how-to/episodes-and-progression.md) | [Sprites and the HUD](how-to/sprites-and-hud.md) | [Ship a ROM](how-to/ship-a-rom.md) |
| [Enemies](how-to/enemies.md) | [Screens](how-to/screens.md) | [Troubleshooting](how-to/troubleshooting.md) |
| [Weapons](how-to/weapons.md) | [Music and sound](how-to/music-and-sound.md) | |

## Reference: look it up

| A game's files | The engine | The tools |
|---|---|---|
| [Game manifest](reference/game-manifest.md) | [Limits](reference/limits.md) | [Command line](reference/cli.md) |
| [Level format](reference/level-format.md) | [Palettes](reference/palettes.md) | [Build flags](reference/build-flags.md) |
| [Level certificate](reference/level-certificate.md) | [Memory map](reference/memory-map.md) | [Build manifest](reference/build-manifest.md) |
| [Asset formats](reference/asset-formats.md) | [Glossary](reference/glossary.md) | [Scenario format](reference/scenario-format.md) |
| [Screen format](reference/screen-format.md), [song format](reference/song-format.md), [sound](reference/sound.md) | | JSON Schemas in [`schema/`](schema/) |

## Explanation: understand the engine

- [The engine and the game](explanation/engine-and-game.md): what the engine decides, what a game decides, what a game cannot change yet.
- [The hardware](explanation/hardware.md): what the Game Boy Color gives the engine, and the rules it treats as invariants.
- [An engine tour](explanation/engine-tour.md): from a button press to a published frame, with the module that owns each step.
- [Architecture](explanation/architecture.md): the memory, renderer, simulation and publication contracts.
- [Textured walls](explanation/textured-walls.md) and [streamed publication](explanation/streamed-publication.md): the renderer's two hardest parts.
- [Verification](explanation/verification.md): hard gates, golden snapshots and the CI lanes.
- [Performance](explanation/performance.md): what an update costs and what content changes.

## Engine development

[Engine development](engine/README.md) is the contributor's guide: where the
code is, the rules a change keeps, [development](engine/development.md)
(setup, the pinned emulator cores, releases), adding
[routines](engine/add-a-routine.md), [checks](engine/add-a-check.md) and
[screen modes](engine/add-a-screen-mode.md), [the assembler](engine/assembler.md),
[the harness](engine/harness.md) and the [hardware checklist](engine/hardware-checklist.md).
[AGENTS.md](../AGENTS.md) holds every contract in one place.

## The games

- [Sable Outpost](../games/sable_outpost/README.md), the showcase: eighteen
  levels in three episodes, and the game the engine's evidence is recorded on.
- [The starter](../games/starter/README.md): the smallest complete game,
  made to be copied.

## Evidence and history

- [Test report](evidence/TEST_REPORT.md): the v0.11 release ROM's qualification.
- [Performance after textures](evidence/PERFORMANCE_PHASE5.md): the current sustained measurements.
- [Release notes](../RELEASE_NOTES.md): changes by version.
- [Archive](archive/README.md): earlier reports and design documents, kept verbatim; [milestones](../milestones/): results bound to their ROMs.

`python tools/check_docs.py` (in CI's fast lane) keeps every link, command,
CLI subcommand, build flag, manifest key and limit on these pages true.
