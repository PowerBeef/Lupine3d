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
class Game:
    root: Path
    id: str
    title: str
    profiles: tuple[str, ...]
    episodes: tuple[Episode, ...]
    actor_palettes: tuple[str, ...]
    kinds: tuple[Kind, ...]
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
    data = _keys(data, {"$schema", "format", "id", "title", "profiles", "episodes", "actor_palettes", "kinds"},
                 {"format", "id", "title", "episodes", "actor_palettes", "kinds"}, root, "the manifest")
    if data["format"] != GAME_FORMAT:
        raise GameError(_where(root, f"format is {data['format']!r}; this engine reads {GAME_FORMAT!r}"))
    game_id = _string(data["id"], root, "id")
    if not game_id.replace("_", "").isalnum() or not game_id[0].isalpha() or game_id.lower() != game_id:
        raise GameError(_where(root, f"id {game_id!r} must be lower-case letters, digits and underscores, starting with a letter"))
    profiles = data.get("profiles", ["slim"])
    if not isinstance(profiles, list) or not profiles or any(p not in DISPLAY_PROFILES for p in profiles):
        raise GameError(_where(root, f"profiles must be a non-empty list drawn from {', '.join(DISPLAY_PROFILES)}"))
    actor_palettes = _names(data["actor_palettes"], root, "actor_palettes", len(ACTOR_PALETTE_SLOTS))
    return Game(root=root, id=game_id, title=_string(data["title"], root, "title"),
                profiles=tuple(profiles), episodes=_episodes(data["episodes"], root, files),
                actor_palettes=actor_palettes, kinds=_kinds(data["kinds"], actor_palettes, root),
                files=files)


def resolve_game_dir(environ: dict[str, str] | os._Environ = os.environ) -> Path:
    configured = environ.get("LUPINE3D_GAME")
    return Path(configured).resolve() if configured else DEFAULT_GAME_DIR


GAME = load_game(resolve_game_dir())
