# Ship a ROM

A Lupine 3D ROM is a 4 MiB MBC5 cartridge image for the Game Boy Color
(CGB-only), with no cartridge RAM.

## Build the release

```sh
python tools/lupine.py game check --game games/my_game
python tools/lupine.py build --game games/my_game
```

gives `build/games/my_game/lupine3d.gb`, its `.sym` for debuggers, and
`build_manifest.json`, whose `sha256` names the ROM and whose `game` record
lists every source file's hash. Rename the ROM for players as you like; the
engine never reads the file name.

Run the checks in [test your game](test-your-game.md) on that build: the
tour against its goldens, the controller route with `RESTART=1`, and both
pinned cores. Keep the reports with the ROM's SHA-256: evidence is valid for
the identical ROM only.

## The header

`game.json` `rom.header_title` (up to 15 upper-case characters) and
`rom.version` are written into the cartridge header; the build computes the
header and global checksums. Bump `version` for each release players see.

## Players need

- An emulator or flash cartridge that supports the Game Boy Color and MBC5.
  The engine is qualified on the pinned SameBoy (CGB-0 and CGB-E) and mGBA
  cores; it has not been tested on physical hardware or with an original
  boot ROM, so say so.
- The controls: D-pad to move and turn, A to fire, B to open a door, SELECT
  to change weapon (and, on the title, to enter a continue code), START to
  begin and to continue past a screen; left and right on the title choose
  the skill.
- That progress is a four-digit continue code shown after each level.

## Licence and credits

The engine is MIT-licensed ([LICENSE](../../LICENSE)). If your game keeps
art or music copied from the starter or the showcase, it keeps their
provenance ([NOTICE.md](../../NOTICE.md)); your own content is yours.
