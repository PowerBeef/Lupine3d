"""CI's lanes have one definition (tools/ci_lanes.py): the workflow's route
matrix and job commands, the local runner and the release packager all read
it, and the route chunks cover the whole campaign in order."""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from ci_lanes import LANES, ROUTE_CHUNKS  # noqa: E402
from lupine3d_v4 import levels  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
# Workflow steps that set up a runner or summarise evidence (`|| true`)
# rather than verify anything.
PLUMBING = ("python -m pip install", "make -C build/deps/", "cmake ", "python tools/snapshot.py diff ")


def workflow_jobs() -> dict[str, list[str]]:
    """Each job's single-line `run:` commands, in order."""
    jobs: dict[str, list[str]] = {}
    current = None
    in_jobs = False
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line == "jobs:":
            in_jobs = True
            continue
        job = re.match(r"^  ([a-z_-]+):$", line)
        if in_jobs and job:
            current = jobs.setdefault(job.group(1), [])
            continue
        run = re.match(r"^\s+run: (.+)$", line)
        if current is not None and run and run.group(1) != "|":
            current.append(run.group(1).strip())
    return jobs


def route_matrix() -> list[tuple[str, str]]:
    text = WORKFLOW.read_text(encoding="utf-8")
    route = text[text.index("\n  route:\n"):]
    route = route[:route.index("\n    steps:")]
    return re.findall(r'- sectors: (\S+)\n\s+restart: "(1?)"', route)


class CiLaneTests(unittest.TestCase):
    def test_route_chunks_cover_the_campaign_in_order(self):
        expected_first = 1
        for chunk in ROUTE_CHUNKS:
            self.assertEqual(chunk.first, expected_first, chunk)
            self.assertLessEqual(chunk.first, chunk.last, chunk)
            expected_first = chunk.last + 1
        self.assertEqual(expected_first - 1, len(levels.CAMPAIGN_ORDER))
        # Only the chunk that reaches the last sector plays the ending and restarts.
        self.assertEqual([chunk.restart for chunk in ROUTE_CHUNKS], [False] * (len(ROUTE_CHUNKS) - 1) + [True])

    def test_workflow_route_matrix_is_the_chunk_table(self):
        self.assertEqual(route_matrix(), [(chunk.sectors, "1" if chunk.restart else "") for chunk in ROUTE_CHUNKS])

    def test_workflow_jobs_run_the_lane_commands(self):
        jobs = workflow_jobs()
        for name, commands in LANES.items():
            ran = [command for command in jobs[name] if not command.startswith(PLUMBING)]
            self.assertEqual(ran, [" ".join(command) for command in commands], name)

    def test_only_pull_requests_cancel_a_running_ci(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", text)


if __name__ == "__main__":
    unittest.main()
