# Troubleshooting

Every refusal names what is wrong. This page lists the messages you are
likely to meet, grouped by who says them, with what to do. The words in a
message are the engine's own; search this page for them.

## The game loader (`game check`, every build)

Messages start with the manifest's path, then the key: `games/my_game/game.json: kinds[1].palette 'neon' is not one of the actor_palettes (drone, carrier)`.

| Message says | Do |
|---|---|
| `has an unknown key 'kindz'; did you mean 'kinds'?` | fix the spelling: an unknown key is never ignored |
| `is missing 'weapons'` | add the key ([game manifest](../reference/game-manifest.md) marks what is required) |
| `… leaves the game directory` | keep every file inside the game's folder, so it can be copied |
| `… does not exist` | the path is relative to `game.json`; check the file name |
| `… is more than the engine's N: …` | a [limit](../reference/limits.md); the reason after the colon says what fills up |
| `episodes[1] needs an 'opening' screen` / `has an opening screen, but the title screen opens the first episode` | episodes after the first have an `opening`, episodes before the last a `closing` ([episodes](episodes-and-progression.md)) |
| `level … appears twice in the campaign` | a level file is listed in two places |
| `weapons must be listed in the order the player gets them` | sort by `from_level`, `null` last; the first weapon is `from_level: 1` |
| `texture '…' is not used by any theme` / `is used both on doors and on walls` | every texture has one role in some theme; doors get their own |
| `must be [red, green, blue] with each from 0 to 31 (RGB555)` | colours are 0..31, not 0..255: divide 8-bit values by 8 |
| `'…' uses '~', which the screen font does not have` | use upper-case letters, digits, space and `- / . , ! ? : '` |
| `is N pixels wide at scale S; a line fits 152` | shorten the line or lower its scale |
| `at y=…, scale …, leaves the frame` | keep a line's top at 5 or below its bottom at 139 |
| `screens.json has no 'gameover' screen` / `screen '…' is never shown` | author exactly the fixed screens and the ones your episodes name |
| `screen 'title' has fields none; the engine writes skill there` | a screen's field lines are fixed: see [screen format](../reference/screen-format.md) |
| `… is not a record of sprites.json` | the role names a record the sprite manifest lacks |
| `the three channels must have the same number of rows` | pad the shorter channels with `.` |
| `… is not a note from C2 to D#7` | notes are `A4`, `F#3` and so on; no flats |

## The level compiler (`game check`, `level check`, every build)

Messages start with the level: `levels/pump_room.json: REFUSED: …`.

| Message says | Do |
|---|---|
| `readability: sightline is too long (7 > 6)` | break the straight run of floor (door cells count) with a turn or a wall |
| `readability: open rectangle 5x4 exceeds the 4x4 room envelope` | split the room; rooms are at most 4×4 |
| `readability: an ordinary door fails to separate enough walkable cells (3 < 4)` | a door must shut off at least four cells, and must be the only way through: check for a second opening |
| `readability: critical path is too short (9 < 12)` / `has too few turns` | move the first enemy further from the spawn, or add a turn |
| `readability: N walkable cells are unreachable` | connect or fill the floor the spawn cannot reach |
| `readability: exposed material paint is too fragmented` | fewer single-cell islands of machinery paint |
| `v2 gameplay levels require exactly one exit door …` | one door with `"kind": "exit"` and `"unlock": "enemies_cleared"` |
| `exit must be reachable from the player spawn when doors are open` | the exit cell is walled off |
| `actor at cell (x, y) is behind a door that opens only when the enemies are cleared, or unreachable` | move the enemy where the spawn can reach it with the exit door shut |
| `player spawn is only 3 cells from drone; safe_radius_cells requires 5` | move the spawn or the enemy apart |
| `player spawn does not have full collision-radius clearance` | the spawn must be in the middle of a floor cell, away from walls |
| `door … orientation does not match its wall frame` | `horizontal` needs walls east and west, `vertical` north and south |
| `every material-3 cell must have exactly one authored door record` | every `3` in the map needs a door record, and every record a `3` |
| `no card-dropping actor is reachable with the keycard doors shut` | a keycard's carrier must be on the near side of its door |
| `declared drops no actor leaves` / `a level must field the medkit drop its actors leave` | `pickups` lists exactly the drops the level's enemy kinds leave |
| `unknown enemy kinds ['robot']` | a level's `kind` must be one of the game's `kinds` |
| `palette_profile '…' is not a theme of …` | name one of the game's themes |

## The build

| Message says | Do |
|---|---|
| `the resident engine no longer fits the fixed half of bank 0 (N bytes past $4000)` | fewer themes or episodes: each theme costs 36 bytes of bank 0 and each extra episode about 26 |
| `the N screens need … bytes and the screen bank holds 16384` | fewer distinct patterns across screens: shorter text, smaller scales, lines that share tile rows |
| `screens.json screen '…': it needs N distinct 8x8 patterns and a screen holds 128` | the same, for one screen |
| `screens.json screen '…': '…' at y=… straddles two tile rows` | move a field line's `y` so its text stays within one 8-pixel row |
| `the songs need … bytes and the music bank holds 16384` | shorten a song (three bytes a row) |
| `… asset hash mismatch` / `palette differs` | a sprite PNG changed without its record: update the record's `sha256` or palette ([sprites and HUD](sprites-and-hud.md)) |
| `… is made for the slim display profile(s), not 'compact'` | only the showcase builds the historical profiles; drop the `--display` option |

## At run time

| Symptom | Look at |
|---|---|
| `lupine run` fails: `snapshot suite 'tour' differs from its goldens: 03_airlock_open (changed, 412 px)` | `snapshot … diff --suite tour` and its `report.html`; accept only an intended change, with a note |
| a frame is refused (`validate_frame`) | an engine bug, not your content: report it with the scenario and the ROM's SHA-256 |
| the controller route stalls or dies | its `report.json` names the level, pose and last exchanges; run that level alone with `SECTORS=N-N` ([debug a build](debug-a-build.md)) |
| the core smoke fails `starting_door_open` | list the door nearest the spawn first in your first level, within a short walk ([test your game](test-your-game.md)) |
