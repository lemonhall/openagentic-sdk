import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.list_dir import ListTool


class TestListToolUnit(unittest.TestCase):
    def test_tree_output_includes_dirs_and_files(self) -> None:
        tool = ListTool(limit=100)
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "sub").mkdir()
            (root / "sub" / "a.txt").write_text("a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")

            out = tool.run_sync({"path": "."}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["count"], 2)
            self.assertIn("sub/", out["output"])
            self.assertIn("a.txt", out["output"])
            self.assertIn("b.txt", out["output"])

    def test_ignores_junk_dirs(self) -> None:
        tool = ListTool(limit=100)
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("x", encoding="utf-8")
            (root / "ok.txt").write_text("ok", encoding="utf-8")

            out = tool.run_sync({"path": "."}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertIn("ok.txt", out["output"])
            self.assertNotIn(".git", out["output"])

    def test_limit_truncates(self) -> None:
        tool = ListTool(limit=3)
        with TemporaryDirectory() as td:
            root = Path(td)
            for i in range(10):
                (root / f"f{i}.txt").write_text(str(i), encoding="utf-8")

            out = tool.run_sync({"path": "."}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["count"], 3)
            self.assertTrue(out["truncated"])


if __name__ == "__main__":
    unittest.main()

