"""Golden-image snapshot workflow: compare, report, accept, and its failure modes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import snapshot  # noqa: E402


def frame(seed: int, *, poke: tuple[int, int, tuple[int, int, int]] | None = None) -> Image.Image:
    image = Image.new("RGB", (160, 144))
    pixels = image.load()
    for y in range(144):
        for x in range(160):
            pixels[x, y] = ((x * 3 + seed) & 255, (y * 5 + seed) & 255, (x ^ y) & 255)
    if poke:
        x, y, colour = poke
        pixels[x, y] = colour
    return image


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, self.out = base / "snapshots", base / "build" / "snapshots"
        self.kw = dict(profile="test-profile", root=self.root, rom_sha256="rom", configuration_id="cfg", hud_row=120)

    def tearDown(self):
        self.tmp.cleanup()

    def suite(self, mode="check"):
        return snapshot.Suite("unit", mode=mode, output_dir=self.out / "unit", **self.kw)

    def accept(self, scenes=None, note="baseline"):
        return snapshot.accept("unit", scenes, note, profile="test-profile", root=self.root,
                               output_dir=self.out / "unit", accepted_by="tests")

    def test_new_scenes_fail_check_mode_until_accepted_with_a_note(self):
        session = self.suite()
        record = session.observe("a", frame(1))
        self.assertEqual(record["status"], "new")
        with self.assertRaises(SystemExit) as raised:
            session.finish()
        self.assertIn("a (new)", str(raised.exception))
        # The evidence was still written for review.
        report = json.loads((self.out / "unit" / "report.json").read_text())
        self.assertFalse(report["passed"]); self.assertEqual(report["counts"]["new"], 1)
        self.assertTrue((self.out / "unit" / "report.html").is_file())
        with self.assertRaises(SystemExit):
            self.accept(note="   ")
        result = self.accept()
        self.assertEqual(result["accepted"], [("a", "new")])
        manifest = json.loads((self.root / "test-profile" / "unit" / "manifest.json").read_text())
        entry = manifest["scenes"]["a"]
        self.assertEqual(entry["rgb_sha256"], snapshot.rgb_sha256(frame(1)))
        self.assertEqual((entry["rom_sha256"], entry["configuration_id"], entry["accepted_by"], entry["note"]),
                         ("rom", "cfg", "tests", "baseline"))
        # A matching golden now passes, and the golden PNG round-trips exactly.
        session = self.suite()
        self.assertEqual(session.observe("a", frame(1))["status"], "match")
        self.assertTrue(session.finish()["passed"])

    def test_changed_pixels_are_counted_located_and_classified(self):
        session = self.suite("record"); session.observe("a", frame(1)); session.finish(); self.accept()
        session = self.suite()
        record = session.observe("a", frame(1, poke=(10, 130, (255, 255, 255))))
        self.assertEqual(record["status"], "changed")
        self.assertEqual(record["changed_pixels"], 1)
        self.assertEqual(record["bbox"], [10, 130, 11, 131])
        self.assertEqual((record["world_pixels"], record["hud_pixels"]), (0, 1))
        with self.assertRaises(SystemExit) as raised:
            session.finish()
        self.assertIn("a (changed, 1 px)", str(raised.exception))
        diff = Image.open(self.out / "unit" / "diff" / "a.png").convert("RGB")
        self.assertEqual(diff.getpixel((10, 130)), (255, 40, 40))
        self.assertNotEqual(diff.getpixel((0, 0)), (255, 40, 40))
        # Record mode writes the same evidence and never fails.
        session = self.suite("record"); session.observe("a", frame(1, poke=(10, 130, (255, 255, 255))))
        self.assertFalse(session.finish()["passed"])

    def test_missing_scenes_fail_and_accepting_them_retires_the_golden(self):
        session = self.suite("record"); session.observe("a", frame(1)); session.observe("b", frame(2)); session.finish(); self.accept()
        session = self.suite(); session.observe("a", frame(1))
        with self.assertRaises(SystemExit) as raised:
            session.finish()
        self.assertIn("b (missing)", str(raised.exception))
        self.accept(["b"], note="scene retired")
        manifest = json.loads((self.root / "test-profile" / "unit" / "manifest.json").read_text())
        self.assertEqual(list(manifest["scenes"]), ["a"])
        self.assertFalse((self.root / "test-profile" / "unit" / "b.png").exists())

    def test_a_golden_that_disagrees_with_its_manifest_is_refused(self):
        session = self.suite("record"); session.observe("a", frame(1)); session.finish(); self.accept()
        frame(9).save(self.root / "test-profile" / "unit" / "a.png")
        with self.assertRaises(AssertionError):
            self.suite().observe("a", frame(1))

    def test_accepting_an_unknown_scene_or_without_a_run_is_refused(self):
        with self.assertRaises(SystemExit):
            self.accept(["a"])
        session = self.suite("record"); session.observe("a", frame(1)); session.finish()
        with self.assertRaises(SystemExit):
            self.accept(["nope"])

    def test_the_first_tour_goldens_equal_the_archived_v010_oracle(self):
        """The v0.10 tour goldens were accepted from the same captures the last
        hash oracle pinned; while that acceptance stands, the two agree."""
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "snapshots" / "slim-sable-v2" / "tour" / "manifest.json"
        archived = json.loads((root / "playtests" / "archive" / "oracles" / "sable_v10_capture_pixels.json").read_text())
        if not manifest_path.is_file():
            self.skipTest("no slim tour goldens accepted yet")
        manifest = json.loads(manifest_path.read_text())
        for capture, digest in archived.items():
            entry = manifest["scenes"].get(Path(capture).stem)
            if entry is None or entry["rom_sha256"] != "76bc716faf798acd4182bbc69e21aa7f0a95b61e7ef7b583bb4b5a680593524c":
                continue  # re-accepted on a later ROM: no longer the v0.10 evidence
            self.assertEqual(entry["rgb_sha256"], digest, capture)


if __name__ == "__main__":
    unittest.main()
