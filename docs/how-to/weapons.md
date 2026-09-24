# Weapons

A game has exactly four weapons (the weapon index is two bits); SELECT walks
to the next one the player owns. Each has a 40×32 sheet of four frames and
two numbers.

```json
"weapons": [
  {"name": "shotgun", "sprite": "shotgun", "damage": 1, "recovery_ticks": 0, "from_level": 1},
  {"name": "slug rifle", "sprite": "slug_rifle", "damage": 2, "recovery_ticks": 15, "from_level": 1},
  {"name": "arc lance", "sprite": "arc_lance", "damage": 4, "recovery_ticks": 40, "from_level": 2},
  {"name": "pulse carbine", "sprite": "pulse_carbine", "damage": 2, "recovery_ticks": 6, "from_level": null}
]
```

| Field | Meaning |
|---|---|
| `sprite` | the sheet's record in the sprite manifest |
| `damage` | health one hit takes off an enemy |
| `recovery_ticks` | simulation ticks before it can fire again; a swap keeps it, so a slow weapon cannot shed its cost by switching |
| `from_level` | the first level that owns it, or `null` for never ([progression](episodes-and-progression.md)) |

## The sheet

Four frames side by side, 40×32 each: idle, the kick, the action pulled
back, the action returning (recovery shows the idle frame). The engine
draws it as ten 8×16 objects, five across and two down, right of centre,
in OBJ palette 0 (a record's `object_palettes` may put whole objects in
palette 5). One weapon's patterns are resident at a time; a swap copies the
next sheet in with the LCD off. Every sheet must compile to exactly 1,280
bytes, so keep to the 40×32 frame.

The showcase renders its weapons from small 3D models so they read as solid
objects at forty pixels ([weapons](../../games/sable_outpost/docs/weapons.md));
any sheet that meets the format works.

## A shot

A shot hits the nearest enemy inside the aim window whose depth is in front
of the wall at the centre of the view (with a quarter-cell of slack, so an
enemy pressed against a wall can still be hit).

## Check

```sh
python tools/lupine.py build --game games/my_game
make playthrough GAME=games/my_game RESTART=1
make sameboy GAME=games/my_game SAMEBOY_DIR=build/deps/SameBoy
```

The swap is a VRAM upload with the LCD off, so run it in a pinned core as
well as the harness ([test your game](test-your-game.md)).
