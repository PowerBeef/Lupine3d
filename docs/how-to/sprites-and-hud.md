# Sprites and the HUD

Every sprite, the HUD chassis and the portrait are indexed PNG sheets,
recorded in your game's sprite manifest (`art/sprites.json`) and given a role
in `game.json` `sprites`. [Asset formats](../reference/asset-formats.md)
lists every role's size and frames.

## Redraw a sheet

1. Edit the PNG at its native size, keeping four palette entries and index 0
   transparent. Frames sit side by side, each the record's `size` wide.
2. Update its record in `art/sprites.json`: the SHA-256 at least, and the
   palette if you changed the PNG's colours:

   ```sh
   python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" games/my_game/art/native/drops.png
   ```

   The build refuses a sheet whose mode, size, transparency, palette or hash
   disagree with its record, so an edited PNG is always a reviewed change.
3. Build and tour it, then accept the changed goldens with a note:

   ```sh
   python tools/lupine.py build --game games/my_game
   python tools/lupine.py run --game games/my_game --snapshot-mode record
   ```

On the console a sprite draws in the OBJ palette of its role
([palettes](../reference/palettes.md)): the PNG's colours are for you.

## Give a role a new sheet

Add a record to `art/sprites.json` (file, size, frames, ticks, anchor,
palette, sha256) and point the role at it in `game.json`:

```json
"sprites": {"manifest": "art/sprites.json", "actor_near": "robot_near", "…": "…"}
```

`python tools/lupine.py game check` refuses a role whose record is missing
or whose file is not in the game.

## The enemy

One set of twelve frames (idle, walk, attack, hurt and death) at three
distances (`actor_near` 16×32, `actor_mid` 16×16, `actor_far` 8×16) draws
every enemy kind; each kind has its own palette. The runtime picks the
distance from the enemy's projected height and the frame from its state and
the frame's ticks.

## The HUD

The HUD is a 160×24 chassis (`hud`) with a 16×16 portrait (`portrait`: four
frames, normal, blink, hurt and dead) and the engine's live fields: health,
the count of living enemies and the objective words. The chassis may use 94
of the HUD's 96 patterns. The words come from `game.json` `hud.words`: a
four-character caption in the 3×5 font over a four-character status in the
5×7 HUD font:

```json
"hud": {"words": {"caption": "GOAL", "hunt": "HUNT", "exit": "EXIT", "dead": "DEAD", "done": "DONE"}}
```

Keep the chassis's field boxes where the engine writes: the showcase's
[steel HUD](../../games/sable_outpost/docs/steel-hud.md) documents the
layout its chassis follows.
