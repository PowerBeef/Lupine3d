"""The CI lanes: one definition for `.github/workflows/ci.yml`, `tools/ci_local.py`
and the release packager.

The controller route plays the campaign in chunks, each on its own runner, so
the slowest chunk and not the whole campaign sets CI's wall clock. A chunk
enters its first sector by continue code (the first from the title); the last
chunk plays the ending and restarts the campaign. `release_check.py` unions
every chunk's report for the current ROM.

Chunks are sized by measured route updates on the overlap-default ROM
(`0f3bcb50`; CI plays about 1,000 updates in 4.4 minutes): no chunk is above
about 3,700 updates, where one chunk used to play 5,600. Sector 10 alone is
3,000. When a route change moves a sector's count by much, re-balance here;
`tests/test_ci_lanes.py` holds the workflow's matrix to this table.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteChunk:
    first: int
    last: int
    restart: bool = False

    @property
    def sectors(self) -> str:
        return f"{self.first}-{self.last}"

    @property
    def directory(self) -> str:
        return f"build/playthrough-{self.sectors}"

    def make_command(self) -> list[str]:
        return ["make", "playthrough", f"SECTORS={self.sectors}", f"ROUTE_DIR={self.directory}"] + (
            ["RESTART=1"] if self.restart else [])


# Measured updates per chunk: 3,617 / 3,188 / 2,779 / 3,043 / 3,707 / 2,907 /
# 3,456 / 1,750 plus the ending and the restart.
ROUTE_CHUNKS = (
    RouteChunk(1, 4),
    RouteChunk(5, 7),
    RouteChunk(8, 9),
    RouteChunk(10, 10),
    RouteChunk(11, 13),
    RouteChunk(14, 15),
    RouteChunk(16, 17),
    RouteChunk(18, 18, restart=True),
)

SAMEBOY_DIR = "build/deps/SameBoy"
MGBA_DIR = "build/deps/mgba"

# The non-route jobs, command for command as ci.yml runs them (the core
# checkout and build steps are CI plumbing: locally the cores must already be
# under build/deps, docs/engine/development.md "Pinned independent cores").
LANES: dict[str, list[list[str]]] = {
    "fast": [
        ["make", "test"],
        ["make", "docs-check"],
        ["make", "playtest", "playtest-world", "playtest-art"],
    ],
    "profiles": [
        ["make", "playtest-sync"],
    ],
    # The starter game (games/starter): a game other than the showcase built,
    # checked, played through on controller input and restarted; the limits
    # game at every maximum; and a new game scaffolded from the starter.
    "starter": [
        ["make", "build", "GAME=games/starter"],
        ["make", "game-check", "GAME=games/starter"],
        ["make", "playtest", "GAME=games/starter"],
        ["make", "playthrough", "GAME=games/starter", "RESTART=1", "ROUTE_DIR=build/games/starter/playthrough"],
        ["make", "limits"],
        ["make", "scaffold-check"],
    ],
    "slow": [
        ["make", "build"],
        ["make", "variants"],
        ["make", "wall-reuse"],
        ["make", "motion"],
        ["make", "sameboy", f"SAMEBOY_DIR={SAMEBOY_DIR}"],
        ["make", "conformance", f"SAMEBOY_DIR={SAMEBOY_DIR}"],
        ["make", "mgba", f"MGBA_DIR={MGBA_DIR}"],
        ["python", "tools/independent_witnesses.py"],
        ["make", "sameboy", "GAME=games/starter", f"SAMEBOY_DIR={SAMEBOY_DIR}"],
    ],
}

# Lanes that need the pinned cores under build/deps.
CORE_LANES = {"slow"}


def route_lane_name(chunk: RouteChunk) -> str:
    return f"route-{chunk.sectors}"


def all_lanes() -> dict[str, list[list[str]]]:
    """Every CI job's commands, the route chunks as `route-A-B` lanes."""
    lanes = dict(LANES)
    for chunk in ROUTE_CHUNKS:
        lanes[route_lane_name(chunk)] = [["make", "build"], chunk.make_command()]
    return lanes
