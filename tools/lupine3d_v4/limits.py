"""What a game can hold: the engine's content limits, in one table.

Every limit is a property of the engine, not of a game, and each carries the
engine fact that sets it, so a creator who meets one knows what it would take
to move it. The game loader (`game.py`) and the level compiler (`levels.py`)
enforce them with messages that name the limit; `docs/reference/limits.md`
is held to this table by the docs check; and `make limits` builds a
generated game with every game-level maximum at once, so the numbers are
proven together, not one at a time.

Standard library only: the loader imports it before anything is built.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    minimum: int
    maximum: int
    what: str        # what is counted, as a creator names it
    why: str         # the engine fact that sets the maximum


LIMITS: dict[str, Limit] = {
    # The campaign.
    "levels": Limit(1, 20, "levels in the campaign",
                    "levels pack five to a ROM bank in banks 241-244; bank 245 holds the weapons"),
    "episodes": Limit(1, 3, "episodes",
                      "each episode after the first adds its screen dispatch to the fixed half of bank 0, "
                      "which keeps 64 bytes free with three"),
    # Enemies and weapons.
    "kinds": Limit(1, 4, "enemy kinds", "an actor's kind is two bits of its slot"),
    "actor_palettes": Limit(1, 3, "enemy palettes",
                            "OBJ palettes 1, 6 and 7 are the enemies'; the other five draw the weapon, drops, "
                            "effects, decor and reticle"),
    "contact_damage": Limit(0, 170, "an enemy's contact damage",
                            "the hard skill adds half again, and the result must fit a byte"),
    "weapons": Limit(4, 4, "weapons", "the weapon index is two bits and SELECT walks all four"),
    # Looks.
    "themes": Limit(1, 4, "themes",
                    "each theme's 36-byte texture directory sits in the fixed half of bank 0 beside the resident "
                    "engine, which leaves 64 bytes with three themes and three episodes"),
    "textures": Limit(1, 7, "wall textures",
                      "a texture is four 5 KiB shade blocks, three to a bank, and the textured kernel owns "
                      "ten banks: thirty blocks"),
    "screen_patterns": Limit(11, 128, "distinct 8x8 patterns on one screen, the ten digits and a blank included",
                             "a screen's patterns are copied to $9000-$97FF, 128 patterns below the map"),
    "hud_word": Limit(1, 4, "characters in a HUD word", "the HUD's objective panel is four characters wide"),
    # Sound.
    "song_rows": Limit(1, 1322, "rows in one song",
                       "a playing song is copied into WRAM bank 5 above the sequencer's state, three bytes a row"),
    # One level (docs/reference/level-format.md).
    "level_size": Limit(16, 16, "cells on a side of a level", "the map is a 16x16 byte grid, one page"),
    "doors_per_level": Limit(0, 6, "doors in a level", "a level's six-byte door records fill 48 bytes of its slot"),
    "actors_per_level": Limit(0, 6, "enemies in a level",
                              "six simulated actor slots; the OBJ budget admits four on screen at once"),
    "fixtures_per_level": Limit(0, 16, "wall fixtures in a level", "a level's fixture records fill 256 bytes"),
}


def limit(name: str) -> Limit:
    return LIMITS[name]


def refuse(name: str, count: int) -> str | None:
    """None when `count` is within limit `name`, else the sentence that says why not."""
    rule = LIMITS[name]
    if rule.minimum <= count <= rule.maximum:
        return None
    if count > rule.maximum:
        return f"{count} {rule.what} is more than the engine's {rule.maximum}: {rule.why}"
    return f"{count} {rule.what} is fewer than the engine's minimum of {rule.minimum}"
