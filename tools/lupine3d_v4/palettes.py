"""The CGB palettes a game's themes become.

A theme (game.json `themes`) gives the world's colours: ceiling and floor,
the structure, door and machinery tones, and the three actor palettes. The
game's `shared_palettes` give the rest, which are the same in every theme:
the HUD (BG 1, which the full-screen modes also use), BG 7, the weapon
(OBJ 0), the drops (OBJ 2), the muzzle flash and decor (OBJ 3), the decor
and the reticle (OBJ 4) and the weapon's second palette (OBJ 5).

Each theme becomes one 128-byte set, BG then OBJ, which `init_palettes`
uploads at every world entry:

    BG 0  ceiling, floor, structure    structure faces, upper half
    BG 1  shared hud                   the HUD and the full-screen modes
    BG 2  floor, floor, structure      structure faces, lower half (Y-flipped)
    BG 3  ceiling, floor, door         door faces, upper
    BG 4  floor, floor, door           door faces, lower
    BG 5  ceiling, floor, machinery    machinery faces, upper
    BG 6  floor, floor, machinery      machinery faces, lower
    BG 7  shared reserved_bg
    OBJ 0 weapon; OBJ 1, 6, 7 the actor palettes; OBJ 2-5 drops, effects,
    decor, weapon_alt

The lower half of the view is the upper half's patterns flipped, and colour
0 of a wall pattern is the space outside the wall: the upper palettes put
the ceiling there and the lower ones the floor, so no pixel is recoloured.

The historical compact and legacy display profiles build only the showcase
and keep the few values they always had: their own HUD colours and, with the
legacy art, the legacy weapon and first-set Sentinel colours.
"""
from __future__ import annotations

from .game import ACTOR_PALETTE_SLOTS, Colour, Game


def rgb15(colour: Colour) -> int:
    red, green, blue = colour
    return red | (green << 5) | (blue << 10)


# The historical profiles' own values, RGB555 (docs/archive: the compact and
# legacy HUDs, and the legacy art's weapon and Sentinel).
_COMPACT_HUD = ((2, 3, 4), (5, 7, 8), (29, 28, 24), (10, 16, 16))
_LEGACY_HUD = ((2, 3, 4), (5, 7, 8), (26, 27, 23), (12, 15, 16))
_LEGACY_WEAPON = ((0, 0, 0), (2, 3, 4), (12, 15, 17), (24, 26, 25))
_LEGACY_SENTINEL = ((0, 0, 0), (3, 2, 3), (20, 5, 4), (28, 24, 17))


def assemble_palette_sets(game: Game, *, slim: bool, compact: bool, sable_art: bool) -> list[tuple[list[int], list[int]]]:
    """(BG, OBJ) RGB555 words for each theme, in theme order."""
    shared = dict(game.shared_palettes)
    if not slim:
        shared["hud"] = _COMPACT_HUD if compact else _LEGACY_HUD
    if not sable_art:
        shared["weapon"] = _LEGACY_WEAPON
    sets = []
    for index, theme in enumerate(game.themes):
        ceiling, floor = theme.ceiling, theme.floor
        bg = [ceiling, floor, *theme.structure, *shared["hud"], floor, floor, *theme.structure,
              ceiling, floor, *theme.door, floor, floor, *theme.door,
              ceiling, floor, *theme.machinery, floor, floor, *theme.machinery, *shared["reserved_bg"]]
        by_slot = {slot: theme.actors[name] for name, slot in zip(game.actor_palettes, ACTOR_PALETTE_SLOTS)}
        if not sable_art and index == 0:
            by_slot[ACTOR_PALETTE_SLOTS[0]] = _LEGACY_SENTINEL
        filler = ((0, 0, 0),) * 4     # an actor palette slot the game does not use
        obj = [*shared["weapon"], *by_slot.get(1, filler), *shared["drops"], *shared["effects"],
               *shared["decor"], *shared["weapon_alt"], *by_slot.get(6, filler), *by_slot.get(7, filler)]
        sets.append(([rgb15(c) for c in bg], [rgb15(c) for c in obj]))
    return sets
