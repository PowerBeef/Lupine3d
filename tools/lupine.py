#!/usr/bin/env python3
"""`lupine`: one entry point for making, building, running and verifying games.

Every subcommand dispatches to the tool that owns the work, in a fresh
process with the profile flags set from the options, because the build
flags are read at import time (AGENTS.md). Nothing here changes what the
tools do; it only spares the reader the flag spelling and the script names.
`--game DIR` (or LUPINE3D_GAME) selects the game; the showcase,
games/sable_outpost, is the default, and any other game builds into
build/games/<id>/.

    lupine new-game DIR [--from GAME] [--title T]   a new game, copied from the starter
    lupine game check                  load the game, compile every level, print what it uses
    lupine build [--sync] [--display slim|compact|legacy] [--output-dir DIR]
    lupine run   [--role tour|world|art] [--scenario FILE] [--snapshot-mode check|record|none]
    lupine snapshot run|diff|accept|list ... (tools/snapshot.py)
    lupine level check FILE...        compile a level and print its certificate
    lupine level info FILE            the level's contents at a glance
    lupine level export-tmx SRC DST   the level as a Tiled map (docs/reference/level-format.md)
    lupine level import-tmx SRC DST   a Tiled map back to JSON, compiled to check it
    lupine profile [--sync]           cycles by main-loop stage on the coherence tour
    lupine test | witnesses | release-check | sable-check [--sync]
    lupine symbols [--sync]           where the debugger exports are and how to load them
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PROFILES = ("slim", "compact", "legacy")
STARTER = ROOT / "games" / "starter"


def select_game(args) -> None:
    """`--game` reaches this process and every tool it starts through
    LUPINE3D_GAME, which the engine reads once at import like every flag."""
    if getattr(args, "game", None):
        os.environ["LUPINE3D_GAME"] = args.game


def load_selected_game():
    """The selected game's manifest, or SystemExit with the loader's reason."""
    sys.path.insert(0, str(TOOLS))
    try:
        from lupine3d_v4 import game as game_module
    except Exception as exc:  # GameError at import: the selected game is refused
        raise SystemExit(f"REFUSED: {exc}") from None
    return game_module.GAME


def profile_env(args) -> dict[str, str]:
    # The profile flags come from the options, never from the caller's
    # environment; the game selection is kept (select_game put --game there).
    env = {k: v for k, v in os.environ.items() if not k.startswith("LUPINE3D_") or k == "LUPINE3D_GAME"}
    display = getattr(args, "display", None)
    if display:
        env["LUPINE3D_DISPLAY"] = display
        if display == "legacy":
            env.update(LUPINE3D_ART="legacy", LUPINE3D_ART_ANIMATION="0")
    if getattr(args, "sync", False):
        env["LUPINE3D_OVERLAP_PUBLICATION"] = "0"
    return env


def run(command: list[str], env: dict[str, str]) -> int:
    print("$", " ".join(str(c) for c in command), flush=True)
    return subprocess.call([str(c) for c in command], cwd=ROOT, env=env)


def output_dir(args) -> Path:
    if getattr(args, "output_dir", None):
        return Path(args.output_dir)
    base = load_selected_game().build_dir(ROOT / "build")
    return base / "sync" if getattr(args, "sync", False) else base


def rom_args(args) -> list[str]:
    out = output_dir(args)
    return ["--rom", out / "lupine3d.gb", "--symbols", out / "lupine3d.sym"]


def cmd_build(args) -> int:
    return run([sys.executable, TOOLS / "build_rom.py", "--output-dir", output_dir(args)], profile_env(args))


def cmd_run(args) -> int:
    command = [sys.executable, TOOLS / "playtest.py", *rom_args(args), "--snapshot-mode", args.snapshot_mode,
               "--role", args.role]
    if args.scenario:
        command += ["--scenario", args.scenario]
    if args.playtest_output:
        command += ["--output-dir", args.playtest_output]
    return run(command, profile_env(args))


def cmd_snapshot(args) -> int:
    return run([sys.executable, TOOLS / "snapshot.py", *args.rest], profile_env(args))


def cmd_level(args) -> int:
    sys.path.insert(0, str(TOOLS))
    from lupine3d_v4 import levels
    if args.action in ("export-tmx", "import-tmx"):
        from lupine3d_v4 import tmx_import
        if len(args.files) != 2:
            print(f"lupine level {args.action} SOURCE DESTINATION")
            return 2
        source, destination = Path(args.files[0]), Path(args.files[1])
        if args.action == "export-tmx":
            tmx_import.export_file(source, destination, swatch=args.swatch)
        else:
            tmx_import.import_file(source, destination)
            levels.compile_level(destination)
        print(f"{source} -> {destination}")
        return 0
    failures = 0
    for path in args.files:
        path = Path(path)
        try:
            level = levels.compile_level(path)
        except Exception as exc:  # the compiler's own message is the report
            print(f"{path}: REFUSED: {exc}")
            failures += 1
            continue
        segments = len(set(level.segment_table) - {0})
        report = level.readability
        if args.action == "check":
            print_certificate(path, level)
        else:
            source = json.loads(path.read_text())
            print(json.dumps({"name": level.name, "format": level.format, "size": [level.width, level.height],
                              "spawn": source.get("player_spawn"), "exit": {"x": level.exit.x, "y": level.exit.y},
                              "doors": [{"id": d.name, "x": d.x, "y": d.y, "flags": d.flags} for d in level.doors],
                              "actors": [{"kind": e.kind, "cell": [e.x_q8 >> 8, e.y_q8 >> 8], "health": e.health}
                                         for e in level.entities],
                              "drops": [{"kind": p.kind, "value": p.value} for p in level.pickups],
                              "fixtures": len(level.fixtures), "segments": segments,
                              "certificate": None if report is None else report.__dict__}, indent=2))
    return 1 if failures else 0


def print_certificate(path: Path, level) -> None:
    segments = len(set(level.segment_table) - {0})
    report = level.readability
    print(f"{path}: ok - {level.name}: {level.width}x{level.height}, {len(level.doors)} doors, "
          f"{len(level.entities)} actors, {len(level.pickups)} drops, {len(level.fixtures)} fixtures, "
          f"{segments} segments")
    if report is not None:
        print(f"  certificate: {report.walkable_cells} walkable, {report.unreachable_cells} unreachable, "
              f"critical path {report.critical_path_steps} steps/{report.critical_path_turns} turns, "
              f"sightline {report.maximum_sightline}, room {report.maximum_open_rectangle[0]}x"
              f"{report.maximum_open_rectangle[1]}, door separation {report.minimum_door_separation}, "
              f"seams {report.material_seams}, singleton runs {report.material_singleton_runs}")


def cmd_game(args) -> int:
    """Load the selected game and compile every level it names: the checks a
    build makes of the content, without building."""
    game = load_selected_game()
    from lupine3d_v4 import game as game_module
    from lupine3d_v4 import levels
    try:
        directory = game.root.relative_to(ROOT)
    except ValueError:
        directory = game.root
    print(f"{game.title} ({game.id}) in {directory}: builds into {game.build_dir(Path('build'))}/")
    print(f"  episodes: {', '.join(f'{e.name} ({len(e.levels)} levels)' for e in game.episodes)}")
    print(f"  kinds: {len(game.kinds)}/{game_module.MAX_KINDS} ({', '.join(k.name for k in game.kinds)}); "
          f"actor palettes {len(game.actor_palettes)}/{len(game_module.ACTOR_PALETTE_SLOTS)}")
    owned = ", ".join(f"{w.name} from level {w.from_level}" if w.from_level else f"{w.name} never"
                      for w in game.weapons)
    print(f"  weapons: {owned}")
    print(f"  themes: {', '.join(game.theme_ids)}; textures: {len(game.texture_names)} ({', '.join(game.texture_names)})")
    print(f"  songs: {', '.join(f'{role} {len(song.pulse)} rows' for role, song in game.songs.items())} "
          f"(at most {game_module.MUSIC_ROW_LIMIT} each)")
    print(f"  playtests: {', '.join(game.playtests) or 'none'}; files read by the build: {len(game.files)}")
    failures = 0
    for episode in game.episodes:
        for path in episode.levels:
            try:
                level = levels.compile_level(path)
            except Exception as exc:  # the compiler's own message is the report
                print(f"{path.relative_to(game.root)}: REFUSED: {exc}")
                failures += 1
                continue
            print_certificate(path.relative_to(game.root), level)
    print("REFUSED" if failures else "ok", f"- {len(game.level_paths) - failures} of {len(game.level_paths)} levels compile")
    return 1 if failures else 0


def compact_json(value, indent: int = 0, width: int = 132, lead: int = 0) -> str:
    """JSON a person edits: a value on one line when it fits (after `lead`
    characters already on its line), else one member per line, so colour
    triples and short records stay readable."""
    flat = json.dumps(value)
    if indent + lead + len(flat) <= width or not isinstance(value, (dict, list)) or not value:
        return flat
    pad = " " * (indent + 2)
    if isinstance(value, dict):
        body = [f"{pad}{json.dumps(key)}: {compact_json(item, indent + 2, width, len(json.dumps(key)) + 2)}"
                for key, item in value.items()]
        return "{\n" + ",\n".join(body) + "\n" + " " * indent + "}"
    return "[\n" + ",\n".join(pad + compact_json(item, indent + 2, width) for item in value) + "\n" + " " * indent + "]"


def cmd_new_game(args) -> int:
    """Copy a game (the starter by default) into a new directory and give
    it its own identity; the copy's goldens are not taken, because a golden
    is a picture of one game."""
    source = Path(args.source).resolve() if args.source else STARTER
    destination = Path(args.directory)
    if not (source / "game.json").is_file():
        print(f"{source}: not a game (no game.json) to copy")
        return 1
    if destination.exists() and any(destination.iterdir()):
        print(f"{destination}: already exists and is not empty; choose a new directory")
        return 1
    game_id = args.id or re.sub(r"[^a-z0-9_]", "_", destination.resolve().name.lower()).strip("_")
    if not game_id or not game_id[0].isalpha():
        game_id = f"game_{game_id}".rstrip("_")
    title = args.title or " ".join(part.capitalize() for part in game_id.split("_") if part)
    header = re.sub(r"[^A-Z0-9 ]", "", title.upper())[:15].strip() or "LUPINE3D"
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("snapshots", "__pycache__", "*.pyc"))
    manifest_path = destination / "game.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id"], manifest["title"] = game_id, title
    manifest.setdefault("rom", {})["header_title"] = header
    manifest["rom"]["version"] = 0
    manifest["profiles"] = ["slim"]     # the historical profiles build only the showcase
    manifest_path.write_text(compact_json(manifest) + "\n", encoding="utf-8")
    sys.path.insert(0, str(TOOLS))
    from lupine3d_v4.game import load_game
    try:
        game = load_game(destination)
    except Exception as exc:  # GameError: the copy names something the loader refuses
        print(f"copied {source} to {destination}, but the copy does not load: {exc}")
        return 1
    shown = destination if not destination.is_absolute() else destination.resolve()
    print(f"Created {shown}: {game.title} ({game.id}), copied from {source.relative_to(ROOT) if source.is_relative_to(ROOT) else source}.")
    print("Next:")
    print(f"  python tools/lupine.py game check --game {shown}")
    print(f"  python tools/lupine.py build --game {shown}      # {game.build_dir(Path('build'))}/lupine3d.gb")
    print(f"  python tools/lupine.py run --game {shown} --snapshot-mode record")
    print(f"  python tools/lupine.py snapshot --game {shown} accept --suite tour --note \"first look\"")
    print("  docs/tutorials/first-game.md walks through the rest.")
    return 0


def cmd_profile(args) -> int:
    return run([sys.executable, TOOLS / "profile_rendering.py"], profile_env(args))


def cmd_test(args) -> int:
    return run(["make", "test"], profile_env(args))


def cmd_witnesses(args) -> int:
    command = [sys.executable, TOOLS / "independent_witnesses.py", "--snapshot-mode", args.snapshot_mode]
    if args.sync:
        command += ["--output-dir", ROOT / "build" / "independent-witnesses-sync"]
    return run(command, profile_env(args))


def cmd_ci(args) -> int:
    return run([sys.executable, TOOLS / "ci_local.py", *args.rest], dict(os.environ))


def cmd_release_check(args) -> int:
    return run([sys.executable, TOOLS / "release_check.py"], profile_env(args))


def cmd_sable_check(args) -> int:
    command = [sys.executable, TOOLS / "check_sable.py", "--snapshot-mode", args.snapshot_mode]
    if args.sync:
        command += ["--output-dir", ROOT / "build" / "sable-v2" / "sync-checks"]
    return run(command, profile_env(args))


def cmd_symbols(args) -> int:
    out = output_dir(args)
    manifest = out / "build_manifest.json"
    if not manifest.is_file():
        print(f"no build under {out}: run `lupine build{' --sync' if args.sync else ''}` first")
        return 1
    exports = json.loads(manifest.read_text()).get("exports")
    if not exports:
        print(f"the build under {out} predates the debugger exports: rebuild it first")
        return 1
    print(f"symbols: {out / 'lupine3d.sym'} ({exports.get('symbols')} entries: {exports.get('code')} code, "
          f"{exports.get('data')} data, {exports.get('ram')} RAM)")
    print(f"map:     {out / 'lupine3d.map'}")
    print("BGB: load the ROM, then Debug > Load symbols. Emulicious: place lupine3d.sym next to lupine3d.gb.")
    print("SameBoy: the debugger reads a .sym beside the ROM automatically.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lupine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def game_option(p):
        p.add_argument("--game", help="the game directory, or a name under games/ (default games/sable_outpost; "
                                      "also LUPINE3D_GAME)")

    def profile_options(p):
        game_option(p)
        p.add_argument("--sync", action="store_true", help="the synchronous publication tail (LUPINE3D_OVERLAP_PUBLICATION=0); overlapped publication is the slim default")
        p.add_argument("--display", choices=PROFILES, help="display profile; legacy implies legacy art")

    p = sub.add_parser("new-game", help="start a game: copy the starter (or --from GAME) into DIR with its own id and title")
    p.add_argument("directory"); p.add_argument("--from", dest="source", help="the game to copy (default games/starter)")
    p.add_argument("--id", help="the new game's id (default: from the directory name)")
    p.add_argument("--title", help="the new game's title (default: from the id)"); p.set_defaults(func=cmd_new_game)
    p = sub.add_parser("game", help="check the selected game: load its manifest and compile every level")
    p.add_argument("action", choices=("check",)); game_option(p); p.set_defaults(func=cmd_game)
    p = sub.add_parser("build", help="build the ROM, listing, symbols, map and manifest"); profile_options(p)
    p.add_argument("--output-dir", help="default the game's build directory (build/ for the showcase), or its sync/ with --sync"); p.set_defaults(func=cmd_build)
    p = sub.add_parser("run", help="run a driven scenario on the built ROM with every frame check"); profile_options(p)
    p.add_argument("--role", choices=("tour", "world", "art"), default="tour", help="which of the game's playtests (game.json playtests)")
    p.add_argument("--scenario"); p.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check")
    p.add_argument("--output-dir", dest="output_dir"); p.add_argument("--playtest-output"); p.set_defaults(func=cmd_run)
    p = sub.add_parser("snapshot", help="golden-image snapshots: run, diff, accept, list"); profile_options(p)
    p.add_argument("rest", nargs=argparse.REMAINDER); p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser("level", help="compile levels and print their certificates; convert to and from Tiled")
    game_option(p)
    p.add_argument("action", choices=("check", "info", "export-tmx", "import-tmx"))
    p.add_argument("files", nargs="+", help="levels to check, or SOURCE DESTINATION for a conversion")
    p.add_argument("--swatch", action="store_true", help="export-tmx: also write materials.png beside the map")
    p.set_defaults(func=cmd_level)
    p = sub.add_parser("profile", help="cycles by main-loop stage over the coherence tour"); profile_options(p); p.set_defaults(func=cmd_profile)
    p = sub.add_parser("test", help="the regression suite (make test)"); p.set_defaults(func=cmd_test)
    p = sub.add_parser("witnesses", help="frozen scenes in every pinned core against the goldens"); profile_options(p)
    p.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check"); p.set_defaults(func=cmd_witnesses)
    sub.add_parser("ci", help="CI's jobs locally, in parallel, before a push; arguments go to tools/ci_local.py")
    p = sub.add_parser("release-check", help="the release verification report"); p.set_defaults(func=cmd_release_check)
    p = sub.add_parser("sable-check", help="the emitted-ROM Sable qualification checks"); profile_options(p)
    p.add_argument("--snapshot-mode", choices=("check", "record", "none"), default="check"); p.set_defaults(func=cmd_sable_check)
    p = sub.add_parser("symbols", help="where the debugger exports are and how to load them"); profile_options(p)
    p.add_argument("--output-dir"); p.set_defaults(func=cmd_symbols)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["ci"]:
        # Everything after `ci` is ci_local's (argparse will not hand a leading
        # option to a REMAINDER argument).
        return cmd_ci(argparse.Namespace(rest=argv[1:]))
    args = build_parser().parse_args(argv)
    select_game(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
