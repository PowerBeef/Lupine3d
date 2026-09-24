"""The documentation checks: links resolve, commands name real targets, the
generated memory map matches the build the suite just made."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import check_docs  # noqa: E402


class DocumentationTests(unittest.TestCase):
    def test_links_commands_and_memory_map(self):
        self.assertEqual(check_docs.main([]), 0)

    def test_checker_catches_a_broken_link_and_a_missing_target(self):
        problems: list[str] = []
        page = Path(check_docs.ROOT) / "docs" / "README.md"
        check_docs.check_links(page, "[x](NO_SUCH_FILE.md) [ok](engine/development.md)", problems)
        self.assertEqual(len(problems), 1)
        check_docs.check_commands(page, ["make build no-such-target  # make believe"], {"build"}, problems)
        self.assertEqual(len(problems), 2)
        self.assertIn("no-such-target", problems[1])


if __name__ == "__main__":
    unittest.main()
