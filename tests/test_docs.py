"""The documentation checks: links and anchors resolve, commands name real
targets and subcommands, the reference pages say what the code does, and the
generated memory map matches the build the suite just made. Each check is
shown catching the mistake it exists for."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import check_docs  # noqa: E402

ROOT = Path(check_docs.ROOT)


class DocumentationTests(unittest.TestCase):
    def test_links_commands_and_memory_map(self):
        self.assertEqual(check_docs.main([]), 0)

    def test_checker_catches_a_broken_link_and_a_missing_target(self):
        problems: list[str] = []
        page = ROOT / "docs" / "README.md"
        check_docs.check_links(page, "[x](NO_SUCH_FILE.md) [ok](engine/development.md)", problems)
        self.assertEqual(len(problems), 1)
        check_docs.check_commands(page, ["make build no-such-target  # make believe"], {"build"}, problems)
        self.assertEqual(len(problems), 2)
        self.assertIn("no-such-target", problems[1])

    def test_an_anchor_must_name_a_heading(self):
        problems: list[str] = []
        page = ROOT / "docs" / "README.md"
        check_docs.check_anchors(page, "[ok](reference/game-manifest.md#themetextures) "
                                       "[bad](reference/game-manifest.md#no-such-heading)", problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("no-such-heading", problems[0])
        self.assertIn("themetextures", check_docs.heading_slugs("### `theme.textures`\n"))

    def test_a_lupine_command_must_exist_and_be_documented(self):
        known = check_docs.lupine_commands()
        self.assertIn("new-game", known)
        problems: list[str] = []
        check_docs.check_lupine(ROOT / "docs" / "README.md", ["python tools/lupine.py fly --game x"], known, problems)
        self.assertEqual(len(problems), 1)
        problems = []
        check_docs.check_cli_reference(known | {"teleport"}, problems)
        self.assertEqual(problems, ["docs/reference/cli.md: `lupine teleport` has no section"])

    def test_every_build_flag_is_documented_and_every_documented_flag_exists(self):
        problems: list[str] = []
        code = check_docs.code_flags()
        self.assertIn("LUPINE3D_GAME", code)
        self.assertIn("LUPINE3D_ANCHOR_PACKETS", code)       # built from the rendering flag table
        check_docs.check_build_flags(problems, code | {"LUPINE3D_NEW_THING"})
        self.assertEqual(problems, ["docs/reference/build-flags.md: no row for LUPINE3D_NEW_THING"])
        problems = []
        check_docs.check_build_flags(problems, code - {"LUPINE3D_ROUTE_DEBUG"})
        self.assertEqual(problems, ["docs/reference/build-flags.md: documents LUPINE3D_ROUTE_DEBUG, which no code reads"])

    def test_the_manifest_reference_lists_the_loaders_keys(self):
        text = (ROOT / "docs" / "reference" / "game-manifest.md").read_text(encoding="utf-8")
        problems: list[str] = []
        check_docs.check_manifest_reference(problems, text.replace("| `step_q8` |", "| `speed` |"))
        self.assertEqual(len(problems), 1)
        self.assertIn("`kind`", problems[0])

    def test_a_limit_marker_and_the_limits_table_match_the_engine(self):
        with tempfile.TemporaryDirectory() as scratch:
            page = Path(scratch) / "page.md"
            page.write_text("up to 21<!-- limit:levels --> levels, 3<!-- limit:episodes --> episodes\n")
            problems: list[str] = []
            original = check_docs.ROOT
            try:
                check_docs.ROOT = Path(scratch)
                (Path(scratch) / "docs" / "reference").mkdir(parents=True)
                (Path(scratch) / "docs" / "reference" / "limits.md").write_text(
                    (original / "docs" / "reference" / "limits.md").read_text().replace("| 1 | 20 |", "| 1 | 25 |"))
                check_docs.check_limits([page], problems)
            finally:
                check_docs.ROOT = original
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("says 21 for limit:levels, which is 20", problems[0])
        self.assertIn("limits.md: the table differs", problems[1])

    def test_the_palette_page_marks_the_theme_palettes(self):
        text = (ROOT / "docs" / "reference" / "palettes.md").read_text(encoding="utf-8")
        problems: list[str] = []
        check_docs.check_palette_roles(problems, text.replace("| 7 | the third enemy palette (`actor_palettes[2]`) | *theme* `actors` |",
                                                              "| 7 | the third enemy palette | shared |"))
        self.assertEqual(len(problems), 1)
        self.assertIn("OBJ palettes marked *theme*", problems[0])

    def test_a_backticked_path_or_symbol_must_exist(self):
        problems: list[str] = []
        page = ROOT / "docs" / "README.md"
        check_docs.check_code_references(page, "`tools/lupine.py` `tools/no_such_tool.py` `tools/lupine.py:build_parser` "
                                               "`tools/lupine.py:no_such_function` `games/my_game/game.json`", problems)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("no_such_tool.py", problems[0])
        self.assertIn("has no no_such_function", problems[1])


if __name__ == "__main__":
    unittest.main()
