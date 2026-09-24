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

from .fonts import FONT, HUD_FONT

ROOT = Path(__file__).resolve().parents[2]
GAMES = ROOT / "games"
DEFAULT_GAME_DIR = GAMES / "sable_outpost"
GAME_FORMAT = "lupine-game-v1"
DISPLAY_PROFILES = ("slim", "compact", "legacy")
# What a dead actor can leave: engine behaviour (a medkit heals, a keycard
# opens keycard doors), so the names are the engine's, not a game's.
DROPS = ("medkit", "keycard")
# The kind byte is masked to two bits, so the stat table has four records.
MAX_KINDS = 4
# Enemy colours: OBJ palettes 1, 6 and 7 are the actors'; the others belong
# to the weapon, drops, effects and decor (docs/ART_PIPELINE.md).
ACTOR_PALETTE_SLOTS = (1, 6, 7)
# The weapon index is masked, so the arsenal is exactly this many weapons.
WEAPON_COUNT = 4
# The roles a wall face can have; a theme gives each a texture.
TEXTURE_ROLES = ("structure", "machinery", "door")
# The palettes that are the same in every theme (docs/ART_PIPELINE.md):
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
SCREENS_FORMAT = "lupine-screens-v1"
# Music: the sequencer plays three songs (title, world, victory) on CH2
# (pulse lead), CH3 (wave bass) and CH4 (noise drums); CH1 is the effects'.
SONG_ROLES = ("title", "world", "victory")
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
# manifest (docs/ART_PIPELINE.md gives each role's size and frames).
SPRITE_ROLES = ("actor_near", "actor_mid", "actor_far", "reticle", "muzzle_flash", "hud", "portrait",
                "drops", "hit_effect", "exit_beacon", "fixtures")
# Wall fixtures: four families (the fixture record's kind is two bits), each
# drawn at three distances in the fixture sheet.
FIXTURE_KINDS = 4
SPRITE_SCHEMAS = ("lupine-sprites-v1", "sable.native.v1")
MUSIC_ROW_LIMIT = 1322   # rows per song the sequencer's WRAM page holds (layout.MUSIC_ROW_CAPACITY)


class GameError(ValueError):
    """A game manifest the engine cannot build, with the reason and the fix."""


@dataclass(frozen=True)
class Episode:
    name: str
    levels: tuple[Path, ...]
    opening: str | None      # the screen shown before its first level (not the first episode's: the title opens it)
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
    y: int                   # top pixel row
    colour: int              # BG palette 1 colour index, 0..3
    scale: int               # pixel size of the 3x5 font
    field: str | None = None # a runtime field after the label (its digits come from SCREEN_FIELDS)


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
    screens: dict[str, tuple[ScreenLine, ...]]   # in runtime order: FIXED_SCREENS, then the episode screens
    rom_title: str                               # the cartridge header title
    rom_version: int                             # the cartridge header's mask ROM version byte
    songs: dict[str, Song]                       # by role: title, world, victory
    sound: Sound
    hud_words: dict[str, str]                    # HUD_WORDS -> the text shown
    sprite_manifest: Path                        # the game's sprite manifest (records of indexed PNG sheets)
    sprites: dict[str, str]                      # SPRITE_ROLES -> sprite record name
    fixture_kinds: tuple[str, ...]               # the names a level's fixtures use, in sheet order
    # Every file the loader read, relative to the game directory, with its
    # SHA-256: the build manifest records it so a ROM names its sources.
    files: dict[str, str] = field(default_factory=dict, compare=False)

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
                + tuple(e.opening for e in self.episodes[1:]))


def _where(root: Path, context: str) -> str:
    try:
        name = (root / "game.json").relative_to(ROOT)
    except ValueError:
        name = root / "game.json"
    return f"{name}: {context}"


def _keys(data: object, allowed: set[str], required: set[str], root: Path, context: str) -> dict:
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


def _game_file(root: Path, relative: object, context: str, files: dict[str, str]) -> Path:
    relative = _string(relative, root, context)
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise GameError(_where(root, f"{context} {relative!r} leaves the game directory; "
                                     "a game's files live inside its folder so the folder can be copied"))
    if not path.is_file():
        raise GameError(_where(root, f"{context} {relative!r} does not exist"))
    files[path.relative_to(root.resolve()).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def _episodes(data: object, root: Path, files: dict[str, str]) -> tuple[Episode, ...]:
    if not isinstance(data, list) or not data:
        raise GameError(_where(root, "episodes must be a non-empty list"))
    episodes = []
    for index, raw in enumerate(data):
        context = f"episodes[{index}]"
        raw = _keys(raw, {"name", "levels", "opening", "closing"}, {"name", "levels"}, root, context)
        levels = raw["levels"]
        if not isinstance(levels, list) or not levels:
            raise GameError(_where(root, f"{context}.levels must be a non-empty list of level files"))
        paths = tuple(_game_file(root, level, f"{context}.levels[{n}]", files) for n, level in enumerate(levels))
        first, last = index == 0, index == len(data) - 1
        opening, closing = raw.get("opening"), raw.get("closing")
        if first and opening is not None:
            raise GameError(_where(root, f"{context} has an opening screen, but the title screen opens the first episode"))
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
    if not isinstance(data, list) or not 1 <= len(data) <= MAX_KINDS:
        raise GameError(_where(root, f"kinds must list one to {MAX_KINDS} enemy kinds "
                                     "(the kind byte is two bits wide)"))
    kinds = []
    for index, raw in enumerate(data):
        context = f"kinds[{index}]"
        fields = {"name", "contact_damage", "recovery_ticks", "step_q8", "palette", "drop"}
        raw = _keys(raw, fields, fields, root, context)
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
            contact_damage=_integer(raw, "contact_damage", 0, 170, root, context),
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
        fields = {"name", "sprite", "damage", "recovery_ticks", "from_level"}
        raw = _keys(raw, fields, fields, root, context)
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
    return {_string(name, root, "a texture name"): _game_file(root, path, f"textures.{name}", files)
            for name, path in data.items()}


def _themes(data: object, textures: dict[str, Path], palettes: tuple[str, ...], root: Path) -> tuple[Theme, ...]:
    if not isinstance(data, list) or not data:
        raise GameError(_where(root, "themes must be a non-empty list"))
    themes = []
    for index, raw in enumerate(data):
        context = f"themes[{index}]"
        raw = _keys(raw, {"name", "textures", "colours", "actors"}, {"name", "textures", "colours", "actors"}, root, context)
        roles = _keys(raw["textures"], set(TEXTURE_ROLES), set(TEXTURE_ROLES), root, f"{context}.textures")
        for role, name in roles.items():
            if name not in textures:
                raise GameError(_where(root, f"{context}.textures.{role} {name!r} is not in textures "
                                             f"({', '.join(textures)})"))
        colours = _keys(raw["colours"], {"ceiling", "floor", "structure", "door", "machinery"},
                        {"ceiling", "floor", "structure", "door", "machinery"}, root, f"{context}.colours")
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
    data = _keys(data, set(SHARED_PALETTES), set(SHARED_PALETTES), root, "shared_palettes")
    return {name: _colours(data[name], 4, root, f"shared_palettes.{name}") for name in SHARED_PALETTES}


def _screens(relative: object, episodes: tuple[Episode, ...], root: Path, files: dict[str, str]) -> dict:
    path = _game_file(root, relative, "screens", files)
    context = path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GameError(_where(root, f"{context} is not valid JSON ({error})")) from None
    data = _keys(data, {"$schema", "format", "screens"}, {"format", "screens"}, root, context)
    if data["format"] != SCREENS_FORMAT:
        raise GameError(_where(root, f"{context} format is {data['format']!r}; this engine reads {SCREENS_FORMAT!r}"))
    episode_screens = tuple(e.closing for e in episodes[:-1]) + tuple(e.opening for e in episodes[1:])
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
    screens = {}
    for name in wanted:
        lines = authored[name]
        if not isinstance(lines, list) or not lines:
            raise GameError(_where(root, f"{context} screen {name!r} must be a non-empty list of lines"))
        parsed = []
        for n, raw in enumerate(lines):
            where = f"{context} {name}[{n}]"
            if isinstance(raw, dict) and "field" in raw:
                raw = _keys(raw, {"field", "label", "y", "colour", "scale"}, {"field", "label", "y", "colour"}, root, where)
                text, field_name = _string(raw["label"], root, f"{where}.label"), _string(raw["field"], root, f"{where}.field")
            else:
                raw = _keys(raw, {"text", "y", "colour", "scale"}, {"text", "y", "colour"}, root, where)
                text, field_name = _string(raw["text"], root, f"{where}.text"), None
            raw.setdefault("scale", 1)
            parsed.append(ScreenLine(text=text, y=_integer(raw, "y", 0, 143, root, where),
                                     colour=_integer(raw, "colour", 0, 3, root, where),
                                     scale=_integer(raw, "scale", 1, 4, root, where), field=field_name))
        fields = [line.field for line in parsed if line.field]
        expected = list(SCREEN_FIELDS.get(name, {}))
        if fields != expected:
            shown = ", ".join(expected) if expected else "none"
            raise GameError(_where(root, f"{context} screen {name!r} has fields {fields or 'none'}; the engine writes "
                                         f"{shown} there, in that order"))
        screens[name] = tuple(parsed)
    return screens


def _rom(data: object, root: Path) -> tuple[str, int]:
    data = _keys(data, {"header_title", "version"}, {"header_title"}, root, "rom")
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
    data = _keys(data, {"$schema", "format", "speed", "loop_row", "pulse", "wave", "noise"},
                 {"format", "speed", "loop_row", "pulse", "wave", "noise"}, root, path.name)
    channels = {}
    for channel in ("pulse", "wave", "noise"):
        where = f"{path.name} {channel}"
        raw = _keys(data[channel], {"notes", "rows"}, {"notes", "rows"}, root, where)
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
    data = _keys(data, {"songs", "sound"}, {"songs", "sound"}, root, "audio")
    songs_raw = _keys(data["songs"], set(SONG_ROLES), set(SONG_ROLES), root, "audio.songs")
    songs = {role: _song(_game_file(root, songs_raw[role], f"audio.songs.{role}", files), root, role)
             for role in SONG_ROLES}
    path = _game_file(root, data["sound"], "audio.sound", files)
    sound = _keys(_json_file(path, root, SOUND_FORMAT), {"$schema", "format", "instruments", "effects"},
                  {"format", "instruments", "effects"}, root, path.name)
    instruments = _keys(sound["instruments"], {"pulse", "wave", "noise"}, {"pulse", "wave", "noise"}, root,
                        f"{path.name} instruments")
    pulse = _keys(instruments["pulse"], {"duty", "envelope"}, {"duty", "envelope"}, root, f"{path.name} pulse")
    wave = _keys(instruments["wave"], {"volume", "pattern"}, {"volume", "pattern"}, root, f"{path.name} wave")
    noise = _keys(instruments["noise"], set(DRUMS), set(DRUMS), root, f"{path.name} noise")
    effects = _keys(sound["effects"], set(EFFECTS), set(EFFECTS), root, f"{path.name} effects")
    return songs, Sound(
        pulse_duty=_byte(pulse["duty"], root, f"{path.name} pulse.duty"),
        pulse_envelope=_byte(pulse["envelope"], root, f"{path.name} pulse.envelope"),
        wave_volume=_byte(wave["volume"], root, f"{path.name} wave.volume"),
        wave_pattern=_bytes(wave["pattern"], 16, root, f"{path.name} wave.pattern"),
        drums={drum: _bytes(noise[drum], 4, root, f"{path.name} noise.{drum}") for drum in DRUMS},
        effects={name: _bytes(effects[name], 5, root, f"{path.name} effects.{name}") for name in EFFECTS})


def _hud(data: object, root: Path) -> dict[str, str]:
    data = _keys(data, {"words"}, {"words"}, root, "hud")
    words = _keys(data["words"], set(HUD_WORDS), set(HUD_WORDS), root, "hud.words")
    out = {}
    for name in HUD_WORDS:
        text = _string(words[name], root, f"hud.words.{name}")
        font, face = (FONT, "the 3x5 caption font") if name == "caption" else (HUD_FONT, "the HUD status font")
        if len(text) > 4:
            raise GameError(_where(root, f"hud.words.{name} {text!r} is longer than the panel's four characters"))
        missing = sorted({c for c in text if c not in font})
        if missing:
            raise GameError(_where(root, f"hud.words.{name} {text!r} uses {', '.join(repr(c) for c in missing)}, "
                                         f"which {face} lacks (it has {''.join(sorted(font))})"))
        out[name] = text
    return out


def _sprites(data: object, weapons: tuple, root: Path, files: dict[str, str]) -> tuple[Path, dict[str, str]]:
    data = _keys(data, set(SPRITE_ROLES) | {"manifest"}, set(SPRITE_ROLES) | {"manifest"}, root, "sprites")
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
    keys = {"format", "id", "title", "episodes", "actor_palettes", "kinds", "weapons", "textures", "themes",
            "shared_palettes", "screens", "rom", "audio", "hud", "sprites", "fixture_kinds"}
    data = _keys(data, keys | {"$schema", "profiles"}, keys, root, "the manifest")
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
    weapons = _weapons(data["weapons"], root, 0)
    sprite_manifest, sprites = _sprites(data["sprites"], weapons, root, files)
    return Game(root=root, id=game_id, title=_string(data["title"], root, "title"),
                profiles=tuple(profiles), episodes=episodes,
                screens=_screens(data["screens"], episodes, root, files), rom_title=rom_title, rom_version=rom_version,
                songs=songs, sound=sound, hud_words=_hud(data["hud"], root),
                sprite_manifest=sprite_manifest, sprites=sprites,
                fixture_kinds=_fixture_kinds(data["fixture_kinds"], root),
                actor_palettes=actor_palettes, kinds=_kinds(data["kinds"], actor_palettes, root),
                weapons=weapons, textures=textures,
                themes=_themes(data["themes"], textures, actor_palettes, root),
                shared_palettes=_shared_palettes(data["shared_palettes"], root), files=files)


def resolve_game_dir(environ: dict[str, str] | os._Environ = os.environ) -> Path:
    configured = environ.get("LUPINE3D_GAME")
    return Path(configured).resolve() if configured else DEFAULT_GAME_DIR


GAME = load_game(resolve_game_dir())
