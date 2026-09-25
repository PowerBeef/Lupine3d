"""The game a build makes: its manifest, loaded and checked.

The engine is Lupine 3D; a game is a directory of data it builds into a ROM
(`games/<id>/game.json` and the files it names). This module reads that
manifest and nothing else: it imports only the standard library, so the
level compiler, the layout and the tools can all depend on it, and a test
can load any game without building one.

`GAME` is the game this process builds, chosen once at import time like
every other build flag: `LUPINE3D_GAME` names its directory, and the
showcase, `games/sable_outpost`, is the default. `load_game` is pure, so a
tool can check any game directory in-process; building a different game
still needs a fresh process.

Every path in a manifest is relative to the game directory and must stay
inside it, so a game folder can be copied anywhere. Unknown keys are errors,
with the nearest valid key suggested, so a typo never silently falls back to
a default.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .fonts import FONT, GLYPH_ADVANCE, GLYPH_HEIGHT, HUD_FONT, SCREEN_FACE
from .limits import LIMITS, refuse

ROOT = Path(__file__).resolve().parents[2]
GAMES = ROOT / "games"
DEFAULT_GAME_DIR = GAMES / "sable_outpost"
GAME_FORMAT = "lupine-game-v1"
DISPLAY_PROFILES = ("slim", "compact", "legacy")
# What a dead actor can leave: engine behaviour (a medkit heals, a keycard
# opens keycard doors), so the names are the engine's, not a game's.
DROPS = ("medkit", "keycard")
# The kind byte is masked to two bits, so the stat table has four records.
MAX_KINDS = LIMITS["kinds"].maximum
# Enemy colours: OBJ palettes 1, 6 and 7 are the actors'; the others belong
# to the weapon, drops, effects and decor (docs/reference/asset-formats.md).
ACTOR_PALETTE_SLOTS = (1, 6, 7)
assert len(ACTOR_PALETTE_SLOTS) == LIMITS["actor_palettes"].maximum
# The weapon index is masked, so the arsenal is exactly this many weapons.
WEAPON_COUNT = LIMITS["weapons"].maximum
# The roles a wall face can have; a theme gives each a texture.
TEXTURE_ROLES = ("structure", "machinery", "door")
# The palettes that are the same in every theme (docs/reference/asset-formats.md):
# BG 1 (the HUD and the full-screen modes), BG 7, and OBJ 0 and 2-5.
SHARED_PALETTES = ("hud", "reserved_bg", "weapon", "drops", "effects", "decor", "weapon_alt")

Colour = tuple[int, int, int]     # RGB555 components, 0..31 each, exactly what the console stores
# The full-screen modes the engine shows, in runtime screen-index order; the
# game's episodes name the rest. Each screen's runtime fields (numbers the
# console writes after a label) are fixed by the code that writes them:
# field name -> digits.
FIXED_SCREENS = ("title", "gameover", "ending", "intermission", "password")
SCREEN_FIELDS = {
    "title": {"skill": 1},
    "gameover": {},
    "ending": {"kills": 3, "time": 4},
    "intermission": {"code": 4, "kills": 2, "time": 3},
    "password": {"code": 4},
}
# A debrief (screens.json `debriefs`, one per level but the last) replaces the
# intermission after its level and writes the intermission's fields.
DEBRIEF_FIELDS = SCREEN_FIELDS["intermission"]
# In a debrief's text these become the cleared level's name and the next one's.
DEBRIEF_TOKENS = ("{sector}", "{next}")
SCREENS_FORMAT = "lupine-screens-v1"
# The full-screen map: 20 columns of 8x8 tiles by 18 rows. A screen's steel
# frame takes the outermost ring, so framed reading-face text and images sit
# in columns 1-18 and rows 1-16.
SCREEN_MAP_COLUMNS, SCREEN_MAP_ROWS = 20, 18
# Music: the sequencer plays songs on CH2 (pulse lead), CH3 (wave bass) and
# CH4 (noise drums); CH1 is the effects'. Every game has a title, a world and
# a victory song; the engine also plays a game over and an ending song when a
# game has them, and any other song is one a level can name (`music`).
SONG_ROLES = ("title", "world", "victory")
SONG_EXTRA_ROLES = ("gameover", "ending")
SONG_FORMAT = "lupine-song-v1"
SOUND_FORMAT = "lupine-sound-v1"
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
LOWEST_OCTAVE = 2        # note 0 is C2
NOTE_COUNT = 64          # C2 .. D#7
DRUMS = ("kick", "snare", "hat")
HOLD_STEP, REST_STEP = -1, -2     # '.' holds the previous note, '-' releases the channel
# The CH1 effects the engine triggers, each one write of NR10..NR14.
EFFECTS = ("shoot", "door", "swap", "keycard", "locked", "hurt", "kill", "pickup", "complete")
# The HUD's objective panel: a small caption over a status word. The caption
# reads while enemies remain or the exit is open (GOAL over HUNT or EXIT in
# the showcase); DEAD and DONE replace both. Each is at most four characters.
HUD_WORDS = ("caption", "hunt", "exit", "dead", "done")
# The sprite roles the engine draws, each a record of the game's sprite
# manifest (docs/reference/asset-formats.md gives each role's size and frames).
SPRITE_ROLES = ("actor_near", "actor_mid", "actor_far", "reticle", "muzzle_flash", "hud", "portrait",
                "drops", "hit_effect", "exit_beacon", "fixtures")
# Wall fixtures: four families (the fixture record's kind is two bits), each
# drawn at three distances in the fixture sheet.
FIXTURE_KINDS = 4
SPRITE_SCHEMAS = ("lupine-sprites-v1", "sable.native.v1")
MUSIC_ROW_LIMIT = LIMITS["song_rows"].maximum   # rows per song the sequencer's WRAM page holds (layout.MUSIC_ROW_CAPACITY)
# A game's driven playtests (tools/playtest.py): the tour every build runs,
# and optionally a living-world run and an art tour. Each scenario may name
# a snapshot suite; its goldens live in the game's snapshots/ directory.
PLAYTEST_ROLES = ("tour", "world", "art")


def _required(*names: str) -> tuple[frozenset[str], frozenset[str]]:
    return frozenset(names), frozenset(names)


# Every object a game's files hold: (allowed keys, required keys). The loader
# refuses any other key, naming the nearest; docs/schema/*.schema.json state
# the same (tests/test_game_schema.py holds them equal). Objects keyed by the
# game's own names (a theme's actors, its textures' names) are checked where
# they are read.
_GAME_KEYS = ("format", "id", "title", "episodes", "actor_palettes", "kinds", "weapons", "textures", "themes",
              "shared_palettes", "screens", "rom", "audio", "hud", "sprites", "fixture_kinds")
KEYS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "game": (frozenset(_GAME_KEYS) | {"$schema", "profiles", "playtests", "preview"}, frozenset(_GAME_KEYS)),
    "episode": (frozenset({"name", "levels", "opening", "closing"}), frozenset({"name", "levels"})),
    "kind": _required("name", "contact_damage", "recovery_ticks", "step_q8", "palette", "drop"),
    "weapon": _required("name", "sprite", "damage", "recovery_ticks", "from_level"),
    "theme": _required("name", "textures", "colours", "actors"),
    "theme.textures": _required(*TEXTURE_ROLES),
    "theme.colours": _required("ceiling", "floor", "structure", "door", "machinery"),
    "shared_palettes": _required(*SHARED_PALETTES),
    "rom": (frozenset({"header_title", "version"}), frozenset({"header_title"})),
    "audio": (frozenset({"songs", "sound", "level_songs"}), frozenset({"songs", "sound"})),
    "audio.songs": (frozenset(SONG_ROLES + SONG_EXTRA_ROLES), frozenset(SONG_ROLES)),
    "hud": _required("words"),
    "hud.words": _required(*HUD_WORDS),
    "sprites": _required("manifest", *SPRITE_ROLES),
    "playtests": (frozenset(PLAYTEST_ROLES), frozenset({"tour"})),
    "preview": _required("x", "y", "angle"),
    "screens": (frozenset({"$schema", "format", "screens", "debriefs"}), frozenset({"format", "screens"})),
    "screen": (frozenset({"frame", "lines"}), frozenset({"lines"})),
    "screen.text": (frozenset({"text", "y", "colour", "scale"}), frozenset({"text", "y", "colour"})),
    "screen.field": (frozenset({"field", "label", "y", "colour", "scale"}), frozenset({"field", "label", "y", "colour"})),
    "screen.say": (frozenset({"say", "row", "colour", "column"}), frozenset({"say", "row", "colour"})),
    "screen.say_field": (frozenset({"field", "label", "row", "colour", "column"}), frozenset({"field", "label", "row", "colour"})),
    "screen.image": (frozenset({"image", "row", "column"}), frozenset({"image", "row"})),
    "song": (frozenset({"$schema", "format", "speed", "loop_row", "pulse", "wave", "noise"}),
             frozenset({"format", "speed", "loop_row", "pulse", "wave", "noise"})),
    "song.channel": _required("notes", "rows"),
    "sound": (frozenset({"$schema", "format", "instruments", "effects"}), frozenset({"format", "instruments", "effects"})),
    "sound.instruments": _required("pulse", "wave", "noise"),
    "sound.pulse": _required("duty", "envelope"),
    "sound.wave": _required("volume", "pattern"),
    "sound.noise": _required(*DRUMS),
    "sound.effects": _required(*EFFECTS),
}


class GameError(ValueError):
    """A game manifest the engine cannot build, with the reason and the fix."""


@dataclass(frozen=True)
class Episode:
    name: str
    levels: tuple[Path, ...]
    opening: str | None      # the screen shown before its first level (the first episode's, a prologue, shows after the title)
    closing: str | None      # the screen shown after its last level (not the last episode's: the ending closes it)


@dataclass(frozen=True)
class Kind:
    name: str
    contact_damage: int      # health a touch takes off at the authored skill (half on easy, 1.5x on hard)
    recovery_ticks: int      # simulation ticks between two contacts
    step_q8: int             # distance per step, in 1/256 of a cell
    palette: str             # one of the game's actor palettes
    drop: str                # what it leaves when it dies: medkit or keycard


@dataclass(frozen=True)
class Weapon:
    name: str
    sprite: str              # the weapon's cel sheet in the game's sprite manifest
    damage: int              # health a hit takes off an actor
    recovery_ticks: int      # simulation ticks before it can fire again (kept across a swap)
    from_level: int | None   # the first level (1-based) that owns it; None: never owned


@dataclass(frozen=True)
class Theme:
    """A level's look: its wall textures and the world's colours.

    A level names its theme (`palette_profile`); every world entry uploads
    the theme's palettes and points the textured kernel at its textures."""
    name: str
    textures: dict[str, str]                 # role (structure, machinery, door) -> texture name
    ceiling: Colour
    floor: Colour
    structure: tuple[Colour, Colour]         # the structure faces' two tones
    door: tuple[Colour, Colour]
    machinery: tuple[Colour, Colour]
    actors: dict[str, tuple[Colour, ...]]    # actor palette name -> four colours (colour 0 is transparent)


@dataclass(frozen=True)
class ScreenLine:
    text: str                # a text line's words, or a field's label
    y: int                   # top pixel row (the reading face and images: row * 8)
    colour: int              # BG palette 1 colour index, 0..3
    scale: int               # pixel size of the 3x5 font
    field: str | None = None # a runtime field after the label (its digits come from SCREEN_FIELDS)
    # "small": the 3x5 face at a pixel row and scale; "reading": the 8x8
    # SCREEN_FACE on a tile row; "image": an indexed PNG on the tile grid.
    face: str = "small"
    row: int | None = None       # tile row of a reading-face line or an image
    column: int | None = None    # its first tile column; None centres it
    image: Path | None = None    # an image line's PNG


@dataclass(frozen=True)
class Song:
    speed: int                                   # frames per row
    loop_row: int                                # where the song restarts when it ends
    # Per channel, one value per row: a note index (pulse, wave: 0 is C2) or
    # a drum index (noise: kick, snare, hat), or HOLD_STEP / REST_STEP.
    pulse: tuple[int, ...]
    wave: tuple[int, ...]
    noise: tuple[int, ...]


@dataclass(frozen=True)
class Sound:
    pulse_duty: int                              # NR21: the lead's duty cycle
    pulse_envelope: int                          # NR22: the lead's envelope
    wave_volume: int                             # NR32: the bass's output level
    wave_pattern: tuple[int, ...]                # the 16 bytes of wave RAM (32 four-bit samples)
    drums: dict[str, tuple[int, int, int, int]]  # drum -> NR41..NR44
    effects: dict[str, tuple[int, ...]]          # effect -> NR10..NR14


@dataclass(frozen=True)
class Game:
    root: Path
    id: str
    title: str
    profiles: tuple[str, ...]
    episodes: tuple[Episode, ...]
    actor_palettes: tuple[str, ...]
    kinds: tuple[Kind, ...]
    weapons: tuple[Weapon, ...]
    textures: dict[str, Path]                # texture name -> indexed 16x8 PNG
    themes: tuple[Theme, ...]
    shared_palettes: dict[str, tuple[Colour, ...]]
    screens: dict[str, tuple[ScreenLine, ...]]   # in runtime order: FIXED_SCREENS, the episode screens, the debriefs
    rom_title: str                               # the cartridge header title
    rom_version: int                             # the cartridge header's mask ROM version byte
    songs: dict[str, Song]                       # by name: title, world, victory, then the game's others in order
    sound: Sound
    hud_words: dict[str, str]                    # HUD_WORDS -> the text shown
    sprite_manifest: Path                        # the game's sprite manifest (records of indexed PNG sheets)
    sprites: dict[str, str]                      # SPRITE_ROLES -> sprite record name
    fixture_kinds: tuple[str, ...]               # the names a level's fixtures use, in sheet order
    playtests: dict[str, Path] = field(default_factory=dict)   # PLAYTEST_ROLES -> scenario (tools only)
    # The pose `tools/make_preview.py` films: Q8.8 position and the angle byte.
    preview: tuple[int, int, int] | None = None
    screen_frames: dict[str, bool] = field(default_factory=dict)   # screen name -> steel frame drawn (default)
    debriefs: int = 0                            # debrief screens, one per level but the last, or none
    # Every file the loader read, relative to the game directory, with its
    # SHA-256: the build manifest records it so a ROM names its sources.
    files: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def is_showcase(self) -> bool:
        """The game the engine's own evidence is recorded on (games/sable_outpost)."""
        return self.root == DEFAULT_GAME_DIR.resolve()

    @property
    def snapshot_root(self) -> Path:
        """The game's golden images: snapshots/<profile>/<suite>/ (tools/snapshot.py)."""
        return self.root / "snapshots"

    def build_dir(self, build: Path) -> Path:
        """Where this game's ROM is built: build/ for the showcase, so every
        existing tool and report keeps its paths, build/games/<id>/ otherwise."""
        return build if self.is_showcase else build / "games" / self.id

    def record(self) -> dict:
        """The build manifest's account of the game: what a ROM was built from."""
        try:
            directory = self.root.relative_to(ROOT).as_posix()
        except ValueError:
            directory = str(self.root)
        return {"id": self.id, "title": self.title, "directory": directory, "files": dict(sorted(self.files.items()))}

    @property
    def level_paths(self) -> tuple[Path, ...]:
        return tuple(path for episode in self.episodes for path in episode.levels)

    @property
    def episode_lengths(self) -> tuple[int, ...]:
        return tuple(len(episode.levels) for episode in self.episodes)

    @property
    def episode_starts(self) -> tuple[int, ...]:
        """The level index each episode after the first begins at."""
        starts, total = [], 0
        for length in self.episode_lengths[:-1]:
            total += length
            starts.append(total)
        return tuple(starts)

    @property
    def kind_ids(self) -> dict[str, int]:
        """Kind name to the runtime kind byte: declaration order."""
        return {kind.name: index for index, kind in enumerate(self.kinds)}

    def actor_palette_slot(self, name: str) -> int:
        return ACTOR_PALETTE_SLOTS[self.actor_palettes.index(name)]

    @property
    def theme_ids(self) -> dict[str, int]:
        """Theme name to the level header's palette-set byte: declaration order."""
        return {theme.name: index for index, theme in enumerate(self.themes)}

    @property
    def texture_names(self) -> tuple[str, ...]:
        """Every texture the themes use, in first-use order (structure,
        machinery, door, theme by theme): the order fixes each one's ROM bank."""
        names: list[str] = []
        for theme in self.themes:
            for role in TEXTURE_ROLES:
                if theme.textures[role] not in names:
                    names.append(theme.textures[role])
        return tuple(names)

    @property
    def texture_sets(self) -> tuple[tuple[int, int, int], ...]:
        """Per theme, the texture index of each role."""
        index = {name: n for n, name in enumerate(self.texture_names)}
        return tuple(tuple(index[theme.textures[role]] for role in TEXTURE_ROLES) for theme in self.themes)

    @property
    def door_textures(self) -> frozenset[str]:
        """Textures drawn on doors, which take the door's shade ladder."""
        return frozenset(theme.textures["door"] for theme in self.themes)

    @property
    def episode_screen_names(self) -> tuple[str, ...]:
        """The episode screens in runtime order: every closing, then every opening."""
        return (tuple(e.closing for e in self.episodes[:-1])
                + tuple(e.opening for e in self.episodes if e.opening is not None))

    @property
    def opening_starts(self) -> tuple[int, ...]:
        """The level index each opening screen is shown before, in the order
        of the openings: 0 first when the first episode has a prologue."""
        starts, total = [], 0
        for episode in self.episodes:
            if episode.opening is not None:
                starts.append(total)
            total += len(episode.levels)
        return tuple(starts)

    @property
    def debrief_names(self) -> tuple[str, ...]:
        return tuple(f"debrief_{n}" for n in range(1, self.debriefs + 1))

    @property
    def song_ids(self) -> dict[str, int]:
        """Song name to its index in the sequencer's directory: declaration order."""
        return {name: index for index, name in enumerate(self.songs)}


def _where(root: Path, context: str) -> str:
    try:
        name = (root / "game.json").relative_to(ROOT)
    except ValueError:
        name = root / "game.json"
    return f"{name}: {context}"


def _keys(data: object, allowed: frozenset[str], required: frozenset[str], root: Path, context: str) -> dict:
    if not isinstance(data, dict):
        raise GameError(_where(root, f"{context} must be an object"))
    for key in data:
        if key not in allowed:
            close = difflib.get_close_matches(key, sorted(allowed), n=1)
            hint = f"; did you mean {close[0]!r}?" if close else f"; the keys are {', '.join(sorted(allowed))}"
            raise GameError(_where(root, f"{context} has an unknown key {key!r}{hint}"))
    missing = sorted(required - set(data))
    if missing:
        raise GameError(_where(root, f"{context} is missing {', '.join(repr(k) for k in missing)}"))
    return data


def _string(value: object, root: Path, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise GameError(_where(root, f"{context} must be a non-empty string"))
    return value


def _game_file(root: Path, relative: object, context: str, files: dict[str, str] | None) -> Path:
    """A file the manifest names; recorded in `files` (with its hash) when the build reads it."""
    relative = _string(relative, root, context)
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise GameError(_where(root, f"{context} {relative!r} leaves the game directory; "
                                     "a game's files live inside its folder so the folder can be copied"))
    if not path.is_file():
        raise GameError(_where(root, f"{context} {relative!r} does not exist"))
    if files is not None:
        files[path.relative_to(root.resolve()).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def _limit(name: str, count: int, root: Path, context: str) -> None:
    reason = refuse(name, count)
    if reason is not None:
        raise GameError(_where(root, f"{context}: {reason}"))


def _episodes(data: object, root: Path, files: dict[str, str]) -> tuple[Episode, ...]:
    if not isinstance(data, list) or not data:
        raise GameError(_where(root, "episodes must be a non-empty list"))
    _limit("episodes", len(data), root, "episodes")
    _limit("levels", sum(len(raw.get("levels", ())) for raw in data if isinstance(raw, dict)), root, "episodes")
    episodes = []
    for index, raw in enumerate(data):
        context = f"episodes[{index}]"
        raw = _keys(raw, *KEYS["episode"], root, context)
        levels = raw["levels"]
        if not isinstance(levels, list) or not levels:
            raise GameError(_where(root, f"{context}.levels must be a non-empty list of level files"))
        paths = tuple(_game_file(root, level, f"{context}.levels[{n}]", files) for n, level in enumerate(levels))
        first, last = index == 0, index == len(data) - 1
        opening, closing = raw.get("opening"), raw.get("closing")
        if last and closing is not None:
            raise GameError(_where(root, f"{context} has a closing screen, but the ending screen closes the last episode"))
        if not first and opening is None:
            raise GameError(_where(root, f"{context} needs an 'opening' screen: it is shown before the episode's first level"))
        if not last and closing is None:
            raise GameError(_where(root, f"{context} needs a 'closing' screen: it is shown after the episode's last level"))
        episodes.append(Episode(
            name=_string(raw["name"], root, f"{context}.name"), levels=paths,
            opening=None if opening is None else _string(opening, root, f"{context}.opening"),
            closing=None if closing is None else _string(closing, root, f"{context}.closing")))
    seen: dict[Path, str] = {}
    for episode in episodes:
        for path in episode.levels:
            if path in seen:
                raise GameError(_where(root, f"level {path.name} appears twice in the campaign"))
            seen[path] = episode.name
    return tuple(episodes)


def _names(data: object, root: Path, context: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(data, list) or not 1 <= len(data) <= maximum:
        raise GameError(_where(root, f"{context} must list one to {maximum} names"))
    names = tuple(_string(name, root, f"{context}[{n}]") for n, name in enumerate(data))
    if len(set(names)) != len(names):
        raise GameError(_where(root, f"{context} names must be distinct"))
    return names


def _integer(record: dict, key: str, minimum: int, maximum: int, root: Path, context: str) -> int:
    value = record[key]
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise GameError(_where(root, f"{context}.{key} must be a whole number from {minimum} to {maximum}"))
    return value


def _kinds(data: object, palettes: tuple[str, ...], root: Path) -> tuple[Kind, ...]:
    if not isinstance(data, list) or not data:
        raise GameError(_where(root, "kinds must be a non-empty list of enemy kinds"))
    _limit("kinds", len(data), root, "kinds")
    kinds = []
    for index, raw in enumerate(data):
        context = f"kinds[{index}]"
        raw = _keys(raw, *KEYS["kind"], root, context)
        palette = _string(raw["palette"], root, f"{context}.palette")
        if palette not in palettes:
            raise GameError(_where(root, f"{context}.palette {palette!r} is not one of the actor_palettes "
                                         f"({', '.join(palettes)})"))
        drop = _string(raw["drop"], root, f"{context}.drop")
        if drop not in DROPS:
            raise GameError(_where(root, f"{context}.drop {drop!r} must be one of {', '.join(DROPS)}"))
        kinds.append(Kind(
            name=_string(raw["name"], root, f"{context}.name"),
            # The hard skill adds half again, which must still fit a byte.
            contact_damage=_integer(raw, "contact_damage", 0, LIMITS["contact_damage"].maximum, root, context),
            recovery_ticks=_integer(raw, "recovery_ticks", 0, 255, root, context),
            step_q8=_integer(raw, "step_q8", 1, 255, root, context),
            palette=palette, drop=drop))
    if len({kind.name for kind in kinds}) != len(kinds):
        raise GameError(_where(root, "kind names must be distinct"))
    return tuple(kinds)


def _weapons(data: object, root: Path, level_count: int) -> tuple[Weapon, ...]:
    if not isinstance(data, list) or len(data) != WEAPON_COUNT:
        raise GameError(_where(root, f"weapons must list exactly {WEAPON_COUNT} weapons "
                                     "(the weapon index is masked to two bits)"))
    weapons = []
    for index, raw in enumerate(data):
        context = f"weapons[{index}]"
        raw = _keys(raw, *KEYS["weapon"], root, context)
        from_level = raw["from_level"]
        if from_level is not None:
            from_level = _integer(raw, "from_level", 1, 255, root, context)
        weapons.append(Weapon(
            name=_string(raw["name"], root, f"{context}.name"),
            sprite=_string(raw["sprite"], root, f"{context}.sprite"),
            damage=_integer(raw, "damage", 1, 255, root, context),
            recovery_ticks=_integer(raw, "recovery_ticks", 0, 255, root, context),
            from_level=from_level))
    if weapons[0].from_level != 1:
        raise GameError(_where(root, "weapons[0].from_level must be 1: the player starts every level with the first weapon"))
    owned = [w.from_level for w in weapons if w.from_level is not None]
    if owned != sorted(owned) or any(w.from_level is not None for w in weapons[len(owned):]):
        raise GameError(_where(root, "weapons must be listed in the order the player gets them: "
                                     "from_level never decreases, and weapons never owned (null) come last"))
    return tuple(weapons)


def _colour(value: object, root: Path, context: str) -> Colour:
    if (not isinstance(value, list) or len(value) != 3
            or any(not isinstance(c, int) or isinstance(c, bool) or not 0 <= c <= 31 for c in value)):
        raise GameError(_where(root, f"{context} must be [red, green, blue] with each from 0 to 31 (RGB555)"))
    return tuple(value)


def _colours(value: object, count: int, root: Path, context: str) -> tuple[Colour, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise GameError(_where(root, f"{context} must list {count} colours"))
    return tuple(_colour(c, root, f"{context}[{n}]") for n, c in enumerate(value))


def _textures(data: object, root: Path, files: dict[str, str]) -> dict[str, Path]:
    if not isinstance(data, dict) or not data:
        raise GameError(_where(root, "textures must map texture names to PNG files"))
    _limit("textures", len(data), root, "textures")
    return {_string(name, root, "a texture name"): _game_file(root, path, f"textures.{name}", files)
            for name, path in data.items()}


def _themes(data: object, textures: dict[str, Path], palettes: tuple[str, ...], root: Path) -> tuple[Theme, ...]:
    if not isinstance(data, list) or not data:
        raise GameError(_where(root, "themes must be a non-empty list"))
    _limit("themes", len(data), root, "themes")
    themes = []
    for index, raw in enumerate(data):
        context = f"themes[{index}]"
        raw = _keys(raw, *KEYS["theme"], root, context)
        roles = _keys(raw["textures"], *KEYS["theme.textures"], root, f"{context}.textures")
        for role, name in roles.items():
            if name not in textures:
                raise GameError(_where(root, f"{context}.textures.{role} {name!r} is not in textures "
                                             f"({', '.join(textures)})"))
        colours = _keys(raw["colours"], *KEYS["theme.colours"], root, f"{context}.colours")
        actors = _keys(raw["actors"], set(palettes), set(palettes), root, f"{context}.actors")
        themes.append(Theme(
            name=_string(raw["name"], root, f"{context}.name"), textures=dict(roles),
            ceiling=_colour(colours["ceiling"], root, f"{context}.colours.ceiling"),
            floor=_colour(colours["floor"], root, f"{context}.colours.floor"),
            structure=_colours(colours["structure"], 2, root, f"{context}.colours.structure"),
            door=_colours(colours["door"], 2, root, f"{context}.colours.door"),
            machinery=_colours(colours["machinery"], 2, root, f"{context}.colours.machinery"),
            actors={name: _colours(actors[name], 4, root, f"{context}.actors.{name}") for name in palettes}))
    if len({theme.name for theme in themes}) != len(themes):
        raise GameError(_where(root, "theme names must be distinct"))
    used = {theme.textures[role] for theme in themes for role in TEXTURE_ROLES}
    for name in textures:
        if name not in used:
            raise GameError(_where(root, f"texture {name!r} is not used by any theme"))
    doors = {theme.textures["door"] for theme in themes}
    walls = {theme.textures[role] for theme in themes for role in ("structure", "machinery")}
    if doors & walls:
        raise GameError(_where(root, f"texture {sorted(doors & walls)[0]!r} is used both on doors and on walls; "
                                     "doors take their own shade ladder, so give them their own texture"))
    return tuple(themes)


def _shared_palettes(data: object, root: Path) -> dict[str, tuple[Colour, ...]]:
    data = _keys(data, *KEYS["shared_palettes"], root, "shared_palettes")
    return {name: _colours(data[name], 4, root, f"shared_palettes.{name}") for name in SHARED_PALETTES}


# A screen draws inside its frame: the inner steel lines run at x 4..155 and
# y 4 and 139.
SCREEN_TEXT_WIDTH = 152
SCREEN_TEXT_TOP, SCREEN_TEXT_BOTTOM = 5, 139


def _screen_text(line: ScreenLine, root: Path, where: str) -> None:
    unknown = sorted({c for c in line.text if c != " " and c not in FONT})
    if unknown:
        raise GameError(_where(root, f"{where} {line.text!r} uses {', '.join(repr(c) for c in unknown)}, which the "
                                     f"screen font does not have (it draws {''.join(FONT)} and space)"))
    width = len(line.text) * GLYPH_ADVANCE * line.scale
    if line.field is None and width > SCREEN_TEXT_WIDTH:
        raise GameError(_where(root, f"{where} {line.text!r} is {width} pixels wide at scale {line.scale}; "
                                     f"a line fits {SCREEN_TEXT_WIDTH} ({SCREEN_TEXT_WIDTH // (GLYPH_ADVANCE * line.scale)} "
                                     "characters at that scale)"))
    if line.y < SCREEN_TEXT_TOP or line.y + GLYPH_HEIGHT * line.scale > SCREEN_TEXT_BOTTOM:
        raise GameError(_where(root, f"{where} at y={line.y}, scale {line.scale}, leaves the frame: a line's "
                                     f"top is at least {SCREEN_TEXT_TOP} and its bottom above {SCREEN_TEXT_BOTTOM}"))


def _reading_text(text: str, row: int, column: int | None, cells: int, frame: bool,
                  root: Path, where: str) -> None:
    """A reading-face line: glyphs the face has, on the map, inside the frame."""
    unknown = sorted({c for c in text if c != " " and c not in SCREEN_FACE})
    if unknown:
        raise GameError(_where(root, f"{where} {text!r} uses {', '.join(repr(c) for c in unknown)}, which the "
                                     f"reading face does not have (it draws {''.join(SCREEN_FACE)} and space)"))
    first, last = (1, SCREEN_MAP_COLUMNS - 2) if frame else (0, SCREEN_MAP_COLUMNS - 1)
    top, bottom = (1, SCREEN_MAP_ROWS - 2) if frame else (0, SCREEN_MAP_ROWS - 1)
    if not top <= row <= bottom:
        raise GameError(_where(root, f"{where} is on row {row}; a {'framed ' if frame else ''}screen's "
                                     f"reading-face rows are {top}-{bottom}"))
    if cells > last - first + 1:
        raise GameError(_where(root, f"{where} {text!r} needs {cells} columns and a {'framed ' if frame else ''}"
                                     f"screen has {last - first + 1}: one character a column"))
    if column is not None and not (first <= column and column + cells - 1 <= last):
        raise GameError(_where(root, f"{where} {text!r} at column {column} runs past column {last}"))


def _screen_lines(name: str, lines: object, fields_wanted: dict[str, int], frame: bool,
                  tokens: dict[str, str], root: Path, context: str, files: dict[str, str]) -> tuple[ScreenLine, ...]:
    if not isinstance(lines, list) or not lines:
        raise GameError(_where(root, f"{context} screen {name!r} must be a non-empty list of lines"))
    parsed = []
    for n, raw in enumerate(lines):
        where = f"{context} {name}[{n}]"
        if not isinstance(raw, dict):
            raise GameError(_where(root, f"{where} must be an object"))
        if "image" in raw:
            raw = _keys(raw, *KEYS["screen.image"], root, where)
            path = _game_file(root, raw["image"], f"{where}.image", files)
            if path.suffix.lower() != ".png":
                raise GameError(_where(root, f"{where}.image must be an indexed PNG"))
            row = _integer(raw, "row", 0, SCREEN_MAP_ROWS - 1, root, where)
            column = _integer(raw, "column", 0, SCREEN_MAP_COLUMNS - 1, root, where) if "column" in raw else None
            parsed.append(ScreenLine(text="", y=row * 8, colour=0, scale=1, face="image", row=row,
                                     column=column, image=path))
            continue
        reading = "say" in raw or ("field" in raw and "row" in raw)
        if reading:
            raw = _keys(raw, *KEYS["screen.say_field" if "field" in raw else "screen.say"], root, where)
            field_name = _string(raw["field"], root, f"{where}.field") if "field" in raw else None
            text = _string(raw["label"] if field_name else raw["say"], root, f"{where}.{'label' if field_name else 'say'}")
            for token, value in tokens.items():
                text = text.replace(token, value)
            row = _integer(raw, "row", 0, SCREEN_MAP_ROWS - 1, root, where)
            column = _integer(raw, "column", 0, SCREEN_MAP_COLUMNS - 1, root, where) if "column" in raw else None
            cells = len(text) + (1 + fields_wanted.get(field_name, 0) if field_name else 0)
            _reading_text(text, row, column, cells, frame, root, where)
            parsed.append(ScreenLine(text=text, y=row * 8, colour=_integer(raw, "colour", 0, 3, root, where),
                                     scale=1, field=field_name, face="reading", row=row, column=column))
            continue
        if "field" in raw:
            raw = _keys(raw, *KEYS["screen.field"], root, where)
            text, field_name = _string(raw["label"], root, f"{where}.label"), _string(raw["field"], root, f"{where}.field")
        else:
            raw = _keys(raw, *KEYS["screen.text"], root, where)
            text, field_name = _string(raw["text"], root, f"{where}.text"), None
        for token, value in tokens.items():
            text = text.replace(token, value)
        raw.setdefault("scale", 1)
        line = ScreenLine(text=text, y=_integer(raw, "y", 0, 143, root, where),
                          colour=_integer(raw, "colour", 0, 3, root, where),
                          scale=_integer(raw, "scale", 1, 4, root, where), field=field_name)
        _screen_text(line, root, where)
        parsed.append(line)
    fields = [line.field for line in parsed if line.field]
    expected = list(fields_wanted)
    if fields != expected:
        shown = ", ".join(expected) if expected else "none"
        raise GameError(_where(root, f"{context} screen {name!r} has fields {fields or 'none'}; the engine writes "
                                     f"{shown} there, in that order"))
    return tuple(parsed)


def _screen_record(raw: object, root: Path, where: str) -> tuple[object, bool]:
    """A screen is a list of lines, or {"frame": false, "lines": [...]}."""
    if isinstance(raw, dict):
        raw = _keys(raw, *KEYS["screen"], root, where)
        frame = raw.get("frame", True)
        if not isinstance(frame, bool):
            raise GameError(_where(root, f"{where}.frame must be true or false"))
        return raw["lines"], frame
    return raw, True


def _level_name(path: Path) -> str:
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("name", path.stem)
    except (OSError, json.JSONDecodeError, AttributeError):
        name = path.stem
    return str(name).upper()


def _screens(relative: object, episodes: tuple[Episode, ...], root: Path,
             files: dict[str, str]) -> tuple[dict, dict[str, bool], int]:
    path = _game_file(root, relative, "screens", files)
    context = path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GameError(_where(root, f"{context} is not valid JSON ({error})")) from None
    data = _keys(data, *KEYS["screens"], root, context)
    if data["format"] != SCREENS_FORMAT:
        raise GameError(_where(root, f"{context} format is {data['format']!r}; this engine reads {SCREENS_FORMAT!r}"))
    episode_screens = (tuple(e.closing for e in episodes[:-1])
                       + tuple(e.opening for e in episodes if e.opening is not None))
    wanted = FIXED_SCREENS + episode_screens
    authored = data["screens"]
    if not isinstance(authored, dict):
        raise GameError(_where(root, f"{context} screens must map screen names to lines"))
    for name in wanted:
        if name not in authored:
            raise GameError(_where(root, f"{context} has no {name!r} screen"
                                         + ("" if name in FIXED_SCREENS else " (an episode names it)")))
    for name in authored:
        if name not in wanted:
            raise GameError(_where(root, f"{context} screen {name!r} is never shown: the engine shows "
                                         f"{', '.join(FIXED_SCREENS)} and the screens your episodes name"))
    screens, frames = {}, {}
    for name in wanted:
        lines, frames[name] = _screen_record(authored[name], root, f"{context} screen {name!r}")
        screens[name] = _screen_lines(name, lines, SCREEN_FIELDS.get(name, {}), frames[name], {},
                                      root, context, files)
    # Debriefs: the screen after each level but the last, in place of the
    # intermission, with the cleared level's name and the next one's.
    debriefs = data.get("debriefs")
    count = 0
    if debriefs is not None:
        levels = [level for episode in episodes for level in episode.levels]
        if not isinstance(debriefs, list) or len(debriefs) != len(levels) - 1:
            raise GameError(_where(root, f"{context} debriefs must list one screen per level but the last: "
                                         f"{len(levels) - 1} for this campaign"))
        for index, raw in enumerate(debriefs):
            name = f"debrief_{index + 1}"
            lines, frames[name] = _screen_record(raw, root, f"{context} debriefs[{index}]")
            tokens = dict(zip(DEBRIEF_TOKENS, (_level_name(levels[index]), _level_name(levels[index + 1]))))
            screens[name] = _screen_lines(name, lines, DEBRIEF_FIELDS, frames[name], tokens, root, context, files)
        count = len(debriefs)
    return screens, frames, count


def _rom(data: object, root: Path) -> tuple[str, int]:
    data = _keys(data, *KEYS["rom"], root, "rom")
    title = _string(data["header_title"], root, "rom.header_title")
    if len(title) > 15 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 " for c in title):
        raise GameError(_where(root, "rom.header_title must be at most 15 upper-case letters, digits or spaces "
                                     "(the cartridge header's title field)"))
    data.setdefault("version", 0)
    return title, _integer(data, "version", 0, 255, root, "rom")


def _json_file(path: Path, root: Path, fmt: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GameError(_where(root, f"{path.name} is not valid JSON ({error})")) from None
    if not isinstance(data, dict) or data.get("format") != fmt:
        raise GameError(_where(root, f"{path.name} must be a {fmt!r} file (its \"format\")"))
    return data


def _byte(value: object, root: Path, context: str) -> int:
    """A register byte: a whole number or a "0x.." string, 0..255."""
    if isinstance(value, str) and value.lower().startswith("0x"):
        try:
            value = int(value, 16)
        except ValueError:
            pass
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
        raise GameError(_where(root, f"{context} must be a byte, 0..255 or \"0x00\"..\"0xFF\""))
    return value


def _bytes(value: object, count: int, root: Path, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise GameError(_where(root, f"{context} must list {count} bytes"))
    return tuple(_byte(v, root, f"{context}[{n}]") for n, v in enumerate(value))


def _note(spec: object, root: Path, context: str) -> int:
    if isinstance(spec, str) and len(spec) >= 2 and spec[:-1] in NOTE_NAMES and spec[-1].isdigit():
        index = (int(spec[-1]) - LOWEST_OCTAVE) * 12 + NOTE_NAMES.index(spec[:-1])
        if 0 <= index < NOTE_COUNT:
            return index
    raise GameError(_where(root, f"{context} {spec!r} is not a note from C2 to D#7 (e.g. \"A4\", \"F#3\")"))


def _song(path: Path, root: Path, role: str) -> Song:
    data = _json_file(path, root, SONG_FORMAT)
    data = _keys(data, *KEYS["song"], root, path.name)
    channels = {}
    for channel in ("pulse", "wave", "noise"):
        where = f"{path.name} {channel}"
        raw = _keys(data[channel], *KEYS["song.channel"], root, where)
        notes = raw["notes"]
        if not isinstance(notes, dict):
            raise GameError(_where(root, f"{where}.notes must map one-letter keys to notes"))
        values = {}
        for key, spec in notes.items():
            if len(key) != 1 or key in ".-":
                raise GameError(_where(root, f"{where}.notes key {key!r} must be one character other than . and -"))
            if channel == "noise":
                if spec not in DRUMS:
                    raise GameError(_where(root, f"{where}.notes {key!r} must be one of {', '.join(DRUMS)}"))
                values[key] = DRUMS.index(spec)
            else:
                values[key] = _note(spec, root, f"{where}.notes {key!r}")
        rows = raw["rows"]
        if not isinstance(rows, list) or not all(isinstance(r, str) for r in rows):
            raise GameError(_where(root, f"{where}.rows must be a list of strings"))
        steps = []
        for step in "".join(rows):
            if step == ".":
                steps.append(HOLD_STEP)
            elif step == "-":
                steps.append(REST_STEP)
            elif step in values:
                steps.append(values[step])
            else:
                raise GameError(_where(root, f"{where}.rows uses {step!r}, which its notes do not define"))
        channels[channel] = tuple(steps)
    if not len(channels["pulse"]) == len(channels["wave"]) == len(channels["noise"]):
        raise GameError(_where(root, f"{path.name}: the three channels must have the same number of rows "
                                     f"({len(channels['pulse'])}, {len(channels['wave'])}, {len(channels['noise'])})"))
    length = len(channels["pulse"])
    if not 1 <= length <= MUSIC_ROW_LIMIT:
        raise GameError(_where(root, f"{path.name} has {length} rows; a song holds 1 to {MUSIC_ROW_LIMIT}"))
    speed = _integer(data, "speed", 1, 255, root, path.name)
    loop = _integer(data, "loop_row", 0, length - 1, root, path.name)
    return Song(speed=speed, loop_row=loop, **channels)


def _audio(data: object, root: Path, files: dict[str, str]) -> tuple[dict[str, Song], Sound]:
    data = _keys(data, *KEYS["audio"], root, "audio")
    songs_raw = _keys(data["songs"], *KEYS["audio.songs"], root, "audio.songs")
    songs = {role: _song(_game_file(root, songs_raw[role], f"audio.songs.{role}", files), root, role)
             for role in SONG_ROLES + SONG_EXTRA_ROLES if role in songs_raw}
    # Songs a level can name (`music` in a level file) besides the world song.
    level_songs = data.get("level_songs", {})
    if not isinstance(level_songs, dict):
        raise GameError(_where(root, "audio.level_songs must map song names to song files"))
    for name, relative in level_songs.items():
        if name in songs or not isinstance(name, str) or not name.replace("_", "").isalnum() or name.lower() != name:
            raise GameError(_where(root, f"audio.level_songs {name!r} must be a new lower-case name "
                                         "(letters, digits and underscores)"))
        songs[name] = _song(_game_file(root, relative, f"audio.level_songs.{name}", files), root, name)
    _limit("songs", len(songs), root, "audio")
    path = _game_file(root, data["sound"], "audio.sound", files)
    sound = _keys(_json_file(path, root, SOUND_FORMAT), *KEYS["sound"], root, path.name)
    instruments = _keys(sound["instruments"], *KEYS["sound.instruments"], root, f"{path.name} instruments")
    pulse = _keys(instruments["pulse"], *KEYS["sound.pulse"], root, f"{path.name} pulse")
    wave = _keys(instruments["wave"], *KEYS["sound.wave"], root, f"{path.name} wave")
    noise = _keys(instruments["noise"], *KEYS["sound.noise"], root, f"{path.name} noise")
    effects = _keys(sound["effects"], *KEYS["sound.effects"], root, f"{path.name} effects")
    return songs, Sound(
        pulse_duty=_byte(pulse["duty"], root, f"{path.name} pulse.duty"),
        pulse_envelope=_byte(pulse["envelope"], root, f"{path.name} pulse.envelope"),
        wave_volume=_byte(wave["volume"], root, f"{path.name} wave.volume"),
        wave_pattern=_bytes(wave["pattern"], 16, root, f"{path.name} wave.pattern"),
        drums={drum: _bytes(noise[drum], 4, root, f"{path.name} noise.{drum}") for drum in DRUMS},
        effects={name: _bytes(effects[name], 5, root, f"{path.name} effects.{name}") for name in EFFECTS})


def _hud(data: object, root: Path) -> dict[str, str]:
    data = _keys(data, *KEYS["hud"], root, "hud")
    words = _keys(data["words"], *KEYS["hud.words"], root, "hud.words")
    out = {}
    for name in HUD_WORDS:
        text = _string(words[name], root, f"hud.words.{name}")
        font, face = (FONT, "the 3x5 caption font") if name == "caption" else (HUD_FONT, "the HUD status font")
        _limit("hud_word", len(text), root, f"hud.words.{name} {text!r}")
        missing = sorted({c for c in text if c not in font})
        if missing:
            raise GameError(_where(root, f"hud.words.{name} {text!r} uses {', '.join(repr(c) for c in missing)}, "
                                         f"which {face} lacks (it has {''.join(sorted(font))})"))
        out[name] = text
    return out


def _sprites(data: object, weapons: tuple, root: Path, files: dict[str, str]) -> tuple[Path, dict[str, str]]:
    data = _keys(data, *KEYS["sprites"], root, "sprites")
    path = _game_file(root, data["manifest"], "sprites.manifest", files)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GameError(_where(root, f"{path.name} is not valid JSON ({error})")) from None
    if not isinstance(manifest, dict) or manifest.get("schema") not in SPRITE_SCHEMAS:
        raise GameError(_where(root, f"{path.name} must be a sprite manifest (\"schema\": \"{SPRITE_SCHEMAS[0]}\")"))
    records = manifest.get("assets", {})
    roles = {role: _string(data[role], root, f"sprites.{role}") for role in SPRITE_ROLES}
    wanted = [(f"sprites.{role}", name) for role, name in roles.items()]
    wanted += [(f"weapons[{n}].sprite", weapon.sprite) for n, weapon in enumerate(weapons)]
    for context, name in wanted:
        if name not in records:
            raise GameError(_where(root, f"{context} {name!r} is not a record of {path.name}"))
        sheet = (path.parent / str(records[name].get("file", ""))).resolve()
        if not sheet.is_relative_to(root.resolve()) or not sheet.is_file():
            raise GameError(_where(root, f"{path.name} record {name!r} names a file that does not exist in the game"))
        files[sheet.relative_to(root.resolve()).as_posix()] = hashlib.sha256(sheet.read_bytes()).hexdigest()
    return path, roles


def _fixture_kinds(data: object, root: Path) -> tuple[str, ...]:
    if not isinstance(data, list) or len(data) != FIXTURE_KINDS:
        raise GameError(_where(root, f"fixture_kinds must name the {FIXTURE_KINDS} wall fixture families, "
                                     "in the order of the fixture sheet"))
    return _names(data, root, "fixture_kinds", FIXTURE_KINDS)


def _playtests(data: object, root: Path) -> dict[str, Path]:
    if data is None:
        return {}
    data = _keys(data, *KEYS["playtests"], root, "playtests")
    # Scenarios drive the built ROM; they are not build inputs, so they are
    # not recorded among the files the ROM was built from.
    return {role: _game_file(root, data[role], f"playtests.{role}", None) for role in PLAYTEST_ROLES if role in data}


def _preview(data: object, root: Path) -> tuple[int, int, int] | None:
    if data is None:
        return None
    data = _keys(data, *KEYS["preview"], root, "preview")
    position = []
    for axis in ("x", "y"):
        value = data[axis]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value < 64:
            raise GameError(_where(root, f"preview.{axis} must be a position in cells, above 0 and below 64"))
        position.append(round(value * 256))
    angle = _integer(data, "angle", 0, 255, root, "preview")
    return position[0], position[1], angle


def load_game(directory: Path) -> Game:
    """Read and check `directory/game.json`; raise GameError naming the problem."""
    root = Path(directory).resolve()
    manifest = root / "game.json"
    if not manifest.is_file():
        raise GameError(f"{root}: no game.json (a game is a directory with a game.json manifest)")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GameError(f"{manifest}: not valid JSON ({error})") from None
    files: dict[str, str] = {"game.json": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    data = _keys(data, *KEYS["game"], root, "the manifest")
    if data["format"] != GAME_FORMAT:
        raise GameError(_where(root, f"format is {data['format']!r}; this engine reads {GAME_FORMAT!r}"))
    game_id = _string(data["id"], root, "id")
    if not game_id.replace("_", "").isalnum() or not game_id[0].isalpha() or game_id.lower() != game_id:
        raise GameError(_where(root, f"id {game_id!r} must be lower-case letters, digits and underscores, starting with a letter"))
    profiles = data.get("profiles", ["slim"])
    if not isinstance(profiles, list) or not profiles or any(p not in DISPLAY_PROFILES for p in profiles):
        raise GameError(_where(root, f"profiles must be a non-empty list drawn from {', '.join(DISPLAY_PROFILES)}"))
    actor_palettes = _names(data["actor_palettes"], root, "actor_palettes", len(ACTOR_PALETTE_SLOTS))
    textures = _textures(data["textures"], root, files)
    episodes = _episodes(data["episodes"], root, files)
    rom_title, rom_version = _rom(data["rom"], root)
    songs, sound = _audio(data["audio"], root, files)
    screens, screen_frames, debriefs = _screens(data["screens"], episodes, root, files)
    weapons = _weapons(data["weapons"], root, 0)
    sprite_manifest, sprites = _sprites(data["sprites"], weapons, root, files)
    return Game(root=root, id=game_id, title=_string(data["title"], root, "title"),
                profiles=tuple(profiles), episodes=episodes,
                screens=screens, screen_frames=screen_frames, debriefs=debriefs,
                rom_title=rom_title, rom_version=rom_version,
                songs=songs, sound=sound, hud_words=_hud(data["hud"], root),
                sprite_manifest=sprite_manifest, sprites=sprites,
                fixture_kinds=_fixture_kinds(data["fixture_kinds"], root),
                actor_palettes=actor_palettes, kinds=_kinds(data["kinds"], actor_palettes, root),
                weapons=weapons, textures=textures,
                themes=_themes(data["themes"], textures, actor_palettes, root),
                shared_palettes=_shared_palettes(data["shared_palettes"], root),
                playtests=_playtests(data.get("playtests"), root), preview=_preview(data.get("preview"), root),
                files=files)


def resolve_game_dir(environ: dict[str, str] | os._Environ = os.environ) -> Path:
    """`LUPINE3D_GAME`: a game directory, or the name of one under games/."""
    configured = environ.get("LUPINE3D_GAME")
    if not configured:
        return DEFAULT_GAME_DIR
    path = Path(configured)
    if not path.is_dir() and not path.is_absolute() and (GAMES / configured).is_dir():
        path = GAMES / configured
    return path.resolve()


GAME = load_game(resolve_game_dir())
