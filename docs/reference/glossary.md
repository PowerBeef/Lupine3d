# Glossary

**Actor.** An enemy in a level: one of six simulated slots, of a *kind*.

**Bank.** A 16 KiB page of the 4 MiB cartridge ROM (MBC5). Bank 0 is always
mapped at `$0000-$3FFF`; one other bank at a time at `$4000-$7FFF`. The
engine's resting bank is bank 1.

**BG, OBJ.** The Game Boy's two kinds of picture: the background layer of
8×8 tiles, where the world and HUD are drawn, and objects (sprites), where
enemies, drops, the weapon and effects are.

**Certificate.** The level compiler's proof that a level is playable and
legible: reachability, clearance, door gates, sightlines, room sizes
([level certificate](level-certificate.md)).

**CGB.** The Game Boy Color. Lupine 3D builds are CGB-only.

**Continue code.** The four digits an intermission shows; typed on the title
(SELECT), they restart the campaign at that level and skill. There is no
cartridge RAM.

**Controller route.** `tools/playthrough.py`: plays a whole game on
controller input alone, with no writes to game RAM, checking every frame.

**Cycles, T-cycles.** The CPU's clock ticks; the unit every timing in the
engine is measured in.

**Driven playtest.** A [scenario](scenario-format.md): poses and buttons
played in the host harness, every frame checked.

**Episode.** A run of levels with an opening and a closing screen.

**Fixed half.** Bank 0, `$0000-$3FFF`: the only ROM that is always mapped,
where resident code (everything that switches banks or that an interrupt
reaches) must live. It is nearly full; see [limits](limits.md).

**Folded compositor.** The world view's lower half is its upper half flipped
vertically, so only eight rows of wall tiles are composed.

**Full geometry update.** One complete recast and recomposition of the world
view, published to the hidden VRAM page and flipped.

**Game.** A directory with a `game.json`: the content the engine builds into
a ROM ([game manifest](game-manifest.md)).

**Golden.** A picture a playtest must reproduce exactly, accepted with a note
and committed under the game's `snapshots/`.

**Harness.** `tools/sm83emu.py`: the deterministic CGB model the engine is
tested in, beside the pinned SameBoy and mGBA cores.

**HUD.** The 160×24 status strip under the world: health, the portrait, the
enemy count and the objective words.

**Kind.** An enemy type: stats, a palette and what it drops. Every kind uses
the same sprite cels.

**Level.** One 16×16 map with its doors, actors, drops and fixtures
([level format](level-format.md)).

**Publication.** Moving a composed frame into VRAM and showing it: patterns
and the map by HBlank DMA during composition, the rest in one VBlank tail.

**Q8, Q5, Q14.** Fixed-point formats: Q8 positions are cells × 256; Q5
projection has five fraction bits; Q14 orders ray crossings exactly.

**Showcase.** Sable Outpost, `games/sable_outpost`: the game the engine's
own evidence is recorded on.

**Snapshot (render).** The immutable copy of the world in WRAM bank 1 that a
frame is rendered from, while simulation runs on in bank 2.

**Theme.** A level's look: its wall textures and the world's palettes.

**Update.** See *full geometry update*.
