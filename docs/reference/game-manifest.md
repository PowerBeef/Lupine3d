# Game manifest (`game.json`)

A game is a directory with a `game.json` at its root. The engine's loader,
`tools/lupine3d_v4/game.py`, is the validator of record: it reads the
manifest and every file it names, refuses an unknown key (and suggests the
nearest), refuses a path that leaves the game's directory, and checks every
[limit](limits.md). `docs/schema/game-v1.schema.json` states the same shape
for an editor; a test holds the schema, the loader and the tables below to
the same keys.

Paths are relative to the game's directory. Colours are **RGB555** triples,
`[red, green, blue]` with each channel 0..31: exactly what the console
stores, so what you write is what you get. Every section below is one JSON
object; *required* keys must be present, the others may be left out.

The [starter game](../../games/starter/game.json) is a complete, small
example; the [showcase](../../games/sable_outpost/game.json) uses every
feature.

### `game`

The top-level object.

| Key | Required | Value |
|---|---|---|
| `format` | yes | `"lupine-game-v1"` |
| `id` | yes | lower-case letters, digits and underscores, starting with a letter. Names the build directory, `build/games/<id>/` |
| `title` | yes | the game's name, for people (reports, the build manifest) |
| `profiles` | no | display profiles the game is made for; default `["slim"]`. Only the showcase builds the historical `compact` and `legacy` profiles |
| `rom` | yes | the cartridge header: [`rom`](#rom) |
| `episodes` | yes | one to three [`episode`](#episode) objects, in play order |
| `actor_palettes` | yes | one to three names for the enemy palettes (OBJ 1, 6 and 7, in that order); a [`kind`](#kind) and every [`theme`](#theme) refer to them |
| `kinds` | yes | one to four [`kind`](#kind) objects; a level's actors name them |
| `weapons` | yes | exactly four [`weapon`](#weapon) objects, in the order the player gets them |
| `ammo` | no | up to two ammunition pool names, in pool order; a weapon's `ammo` and an ammo [`item`](#item) name one |
| `keys` | no | up to two key colour names; key *n* is drawn in the effects palette (the first) or the decor palette (the second), and a card door and a key [`item`](#item) name one |
| `items` | no | up to sixteen [`item`](#item) types a level can place |
| `carry_over` | no | `true`: health (at least 50), armour, ammunition and weapons found carry from a cleared level into the next; a death retries a level with what it began with, and the title's START begins a run from the first level's loadout. Default `false`: every level begins full |
| `textures` | yes | texture name → a 16×8 indexed PNG ([asset formats](asset-formats.md)); one to seven, each used by a theme |
| `themes` | yes | one to four [`theme`](#theme) objects; a level names one as its `palette_profile` |
| `shared_palettes` | yes | the palettes every theme shares: [`shared_palettes`](#shared_palettes) |
| `screens` | yes | the full-screen modes' text: a [screens file](screen-format.md) |
| `audio` | yes | the songs and sound effects: [`audio`](#audio) |
| `hud` | yes | the HUD's words: [`hud`](#hud) |
| `sprites` | yes | which sprite sheet plays which role: [`sprites`](#sprites) |
| `fixture_kinds` | yes | the four wall fixture families, in the order of the fixture sheet; a level's fixtures name them |
| `playtests` | no | the game's driven playtests: [`playtests`](#playtests) |
| `preview` | no | the pose `tools/make_preview.py` films: [`preview`](#preview) |
| `$schema` | no | an editor hint; ignored |

### `rom`

| Key | Required | Value |
|---|---|---|
| `header_title` | yes | up to 15 upper-case letters, digits or spaces: the cartridge header's title field |
| `version` | no | the header's mask ROM version byte, 0..255; default 0 |

### `episode`

| Key | Required | Value |
|---|---|---|
| `name` | yes | the episode's name |
| `levels` | yes | its [level files](level-format.md), in play order. The campaign is every episode's levels in order: at most 20 |
| `opening` | every episode but the first | the screen shown before its first level (the title screen opens the first episode) |
| `closing` | every episode but the last | the screen shown after its last level (the ending closes the last) |

A continue code restores the campaign at any level, and entering an
episode's first level by code shows that episode's opening. Weapons owned
follow the level index, so a code restores the arsenal too.

### `kind`

An enemy kind. Every kind uses the same sprite cels (the `actor_*` sprite
roles) in its own palette, so a kind costs ROM bytes, not VRAM.

| Key | Required | Value |
|---|---|---|
| `name` | yes | what a level's `entities[].kind` says |
| `contact_damage` | yes | health a touch takes at the authored skill, 0..170; half on easy and one and a half on hard |
| `recovery_ticks` | yes | simulation ticks between two touches, 0..255 |
| `step_q8` | yes | distance per step in 1/256 of a cell, 1..255 (8 is a steady walk, 15 a sprint) |
| `palette` | yes | one of `actor_palettes` |
| `drop` | yes | what it leaves when it dies. In a game with `items`: an [`item`](#item) type or `none` (a level may name another per actor); otherwise `medkit` (restores health) or `keycard` (opens the level's keycard doors) |
| `range` | no | a ranged kind: how many cells its shot reaches (Chebyshev), 2..7. It holds its ground in reach and sight, raises its arm for `windup_ticks` (the `warn` sound), then shoots if it still sees the player; a hit while it aims spends the shot. Give all three ranged keys or none |
| `ranged_damage` | with `range` | health a shot takes at the authored skill, 1..170, scaled by skill like `contact_damage` |
| `windup_ticks` | with `range` | AI ticks (a fifteenth of a second each) it aims before the shot; its `recovery_ticks` pass before it aims again |

### `weapon`

The weapon index is two bits, so there are always four; SELECT walks to the
next one the player owns.

| Key | Required | Value |
|---|---|---|
| `name` | yes | the weapon's name |
| `sprite` | yes | its cel sheet: a record of the sprite manifest (40×32, four cels) |
| `damage` | yes | health a hit takes off an enemy, 1..255 |
| `recovery_ticks` | yes | simulation ticks before it fires again, 0..255; kept across a swap |
| `from_level` | yes | the first level (1-based) that owns it, or `null` for never. The first weapon's is 1, and the list never goes back down. A weapon [`item`](#item) also gives it for the rest of that level |
| `ammo` | no | the pool a shot draws on, one of `ammo`. Without it the weapon never runs dry; the first weapon has none, and a dry weapon falls back to it |
| `cost` | no | rounds a shot takes, 1..9; default 1, and only with `ammo` |

### `item`

Something placed on a level's floor ([level format](level-format.md#items)),
taken by walking onto its cell. An item with nothing to give (health or
armour already full, a pool full or infinite) stays where it is.

| Key | Required | Value |
|---|---|---|
| `name` | yes | what a level's `items` call it |
| `sprite` | yes | a cel of the `items` sprite sheet |
| `effect` | yes | `health`, `armour`, `ammo`, `key` or `weapon` |
| `value` | for health, armour and ammo | health given (up to 99), armour points (up to 100) or rounds (up to 99) |
| `pool` | for ammo | the pool it fills, one of `ammo` |
| `key` | for key | the key colour it gives, one of `keys` |
| `weapon` | for weapon | the weapon it gives, by name |
| `palette` | no | the shared OBJ palette it is drawn in: `drops` (the default), `effects` or `decor` |

### `theme`

A level's look: the textures on its walls and the world's colours. Every
entry into a level uploads its theme's palettes with the LCD off
([palettes](palettes.md) gives each colour's slot).

| Key | Required | Value |
|---|---|---|
| `name` | yes | what a level's `palette_profile` says |
| `textures` | yes | [`theme.textures`](#themetextures): a texture for each wall role |
| `colours` | yes | [`theme.colours`](#themecolours) |
| `actors` | yes | every `actor_palettes` name → four colours (colour 0 is transparent) |

### `theme.textures`

| Key | Required | Value |
|---|---|---|
| `structure` | yes | the texture on structure walls (material 1) |
| `machinery` | yes | the texture on machinery walls (material 2) |
| `door` | yes | the texture on doors (material 3). Doors take their own shade ladder, so a door texture is never also a wall texture |

### `theme.colours`

| Key | Required | Value |
|---|---|---|
| `ceiling` | yes | one colour: the space above the walls |
| `floor` | yes | one colour: the space below them |
| `structure` | yes | two colours: a structure wall's light and dark tones |
| `door` | yes | two colours for doors |
| `machinery` | yes | two colours for machinery |

### `shared_palettes`

Four colours each, the same in every theme: the screens and HUD must not
change colour between levels.

| Key | Required | Value |
|---|---|---|
| `hud` | yes | BG 1: the HUD and every full-screen mode |
| `reserved_bg` | yes | BG 7 |
| `weapon` | yes | OBJ 0: the weapon |
| `drops` | yes | OBJ 2: medkits and keycards |
| `effects` | yes | OBJ 3: the muzzle flash and decor |
| `decor` | yes | OBJ 4: decor and the reticle |
| `weapon_alt` | yes | OBJ 5: a weapon's second palette |

### `audio`

| Key | Required | Value |
|---|---|---|
| `songs` | yes | [`audio.songs`](#audiosongs) |
| `level_songs` | no | songs a level can name with its `music` key besides the world song: a lower-case name to a [song file](song-format.md) |
| `sound` | yes | the instruments and effects: a [sound file](sound.md) |

### `audio.songs`

Each is a [song file](song-format.md).

| Key | Required | Value |
|---|---|---|
| `title` | yes | plays on the title screen and code entry |
| `world` | yes | plays in the world, from the start of every level that names no other song |
| `victory` | yes | plays on a cleared level's intermission or debrief, and on the ending when there is no `ending` song |
| `gameover` | no | plays on the game over screen, which is silent without it |
| `ending` | no | plays on the ending |

### `hud`

| Key | Required | Value |
|---|---|---|
| `words` | yes | [`hud.words`](#hudwords) |

### `hud.words`

The HUD's objective panel: a small caption over a status word, each at
most four characters. The caption is drawn in the 3×5 screen font, the
status words in the 5×7 HUD font.

| Key | Required | Value |
|---|---|---|
| `caption` | yes | the caption while enemies remain or the exit is open (`GOAL`) |
| `hunt` | yes | the status while enemies remain (`HUNT`) |
| `exit` | yes | the status once the exit is open (`EXIT`) |
| `dead` | yes | shown alone when the player dies (`DEAD`) |
| `done` | yes | shown alone when the level is complete (`DONE`) |

### `sprites`

Every value but `manifest` names a record of the sprite manifest
([asset formats](asset-formats.md) gives each role's size and cels).

| Key | Required | Value |
|---|---|---|
| `manifest` | yes | the sprite manifest (`art/sprites.json` by convention) |
| `actor_close` | no | the enemy at the closest range, 16×48, as many cels as `actor_near`; without it the near figure is the closest |
| `actor_near` | yes | the enemy at close range, 16×32, twelve cels |
| `actor_mid` | yes | the enemy at middle range, 8×16 or 16×16 |
| `actor_far` | yes | the enemy far away, 8×16 |
| `reticle` | yes | the crosshair, 8×16 |
| `muzzle_flash` | yes | the flash, 8×16, two cels |
| `hud` | yes | the HUD chassis, 160×24 |
| `portrait` | yes | the portrait, 16×16: normal, blink, hurt, dead |
| `drops` | yes | the medkit and keycard, 8×8 |
| `hit_effect` | yes | the hit spark, 8×8, two cels |
| `exit_beacon` | yes | the exit marker, 8×8, two cels |
| `fixtures` | yes | the wall fixtures, 16×16, three distances per family |
| `items` | with items | the placed items' cels, 8×8, one per `item` sprite |

### `playtests`

Driven scenarios `tools/playtest.py` plays on the built ROM with every frame
check ([scenario format](scenario-format.md)). Each scenario names its
snapshot suite, whose goldens live in the game's `snapshots/` directory.

| Key | Required | Value |
|---|---|---|
| `tour` | yes | the tour every build runs (`lupine run`, `make playtest`) |
| `world` | no | a run with the actors alive (`make playtest-world`) |
| `art` | no | an art tour (`make playtest-art`) |

### `preview`

| Key | Required | Value |
|---|---|---|
| `x` | yes | position in cells, above 0 and below 64 (8.5 is the middle of column 8) |
| `y` | yes | position in cells |
| `angle` | yes | the angle byte: 0 faces east, 64 south, 128 west, 192 north |
