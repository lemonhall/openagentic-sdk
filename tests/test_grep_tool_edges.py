import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.grep import GrepTool


class TestGrepToolEdges(unittest.TestCase):
    def test_no_match_returns_empty_matches(self) -> None:
        tool = GrepTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("hello\nworld\n", encoding="utf-8")

            out = tool.run_sync(
                {"query": "NOPE", "file_glob": "**/*.txt", "root": str(root)},
                ToolContext(cwd=str(root), project_dir=str(root)),
            )
            self.assertEqual(out["matches"], [])
            self.assertEqual(out["total_matches"], 0)
            self.assertFalse(out["truncated"])

    def test_case_insensitive_matches(self) -> None:
        tool = GrepTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("Hello\n", encoding="utf-8")

            out = tool.run_sync(
                {"query": "hello", "file_glob": "**/*.txt", "root": str(root), "case_sensitive": False},
                ToolContext(cwd=str(root), project_dir=str(root)),
            )
            self.assertEqual(len(out["matches"]), 1)
            self.assertEqual(out["matches"][0]["line"], 1)

    def test_before_and_after_context(self) -> None:
        tool = GrepTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("a\nMATCH\nc\nd\n", encoding="utf-8")

            out = tool.run_sync(
                {
                    "query": "MATCH",
                    "file_glob": "**/*.txt",
                    "root": str(root),
                    "before_context": 1,
                    "after_context": 2,
                },
                ToolContext(cwd=str(root), project_dir=str(root)),
            )
            self.assertEqual(len(out["matches"]), 1)
            m = out["matches"][0]
            self.assertEqual(m["before_context"], ["a"])
            self.assertEqual(m["after_context"], ["c", "d"])

    def test_crlf_line_numbers(self) -> None:
        tool = GrepTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_bytes(b"a\r\nb\r\n")

            out = tool.run_sync(
                {"query": "b", "file_glob": "**/*.txt", "root": str(root)},
                ToolContext(cwd=str(root), project_dir=str(root)),
            )
            self.assertEqual(len(out["matches"]), 1)
            self.assertEqual(out["matches"][0]["line"], 2)

    def test_max_matches_truncates(self) -> None:
        tool = GrepTool(max_matches=2)
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("x\nx\nx\n", encoding="utf-8")

            out = tool.run_sync(
                {"query": "x", "file_glob": "**/*.txt", "root": str(root)},
                ToolContext(cwd=str(root), project_dir=str(root)),
            )
            self.assertTrue(out["truncated"])
            self.assertEqual(len(out["matches"]), 2)

    def test_root_outside_project_is_rejected(self) -> None:
        tool = GrepTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            outside_root = root.parent
            (outside_root / "outside.txt").write_text("LEAKME\n", encoding="utf-8")
            try:
                with self.assertRaises(ValueError):
                    tool.run_sync(
                        {"query": "LEAKME", "file_glob": "outside.txt", "root": str(outside_root)},
                        ToolContext(cwd=str(root), project_dir=str(root)),
                    )
            finally:
                p = outside_root / "outside.txt"
                if p.exists():
                    p.unlink()


if __name__ == "__main__":
    unittest.main()

