import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.bash import BashTool


class TestBashToolEdges(unittest.TestCase):
    def test_output_lines_truncation_and_full_output_file_written(self) -> None:
        tool = BashTool(max_output_lines=2, timeout_s=5.0)
        with TemporaryDirectory() as td:
            root = Path(td)
            out = tool.run_sync(
                {"command": "printf '1\\n2\\n3\\n4\\n5\\n'"},
                ToolContext(cwd=str(root), project_dir=str(root)),
            )

            self.assertTrue(out["output_lines_truncated"])
            self.assertEqual(out["output"].splitlines(), ["1", "2"])

            full_path = out["full_output_file_path"]
            self.assertIsInstance(full_path, str)
            self.assertTrue(full_path)

            p = Path(full_path).resolve()
            self.assertTrue(p.is_file())
            self.assertTrue(p.is_relative_to(root.resolve()))
            data = p.read_bytes()
            self.assertIn(b"3", data)
            self.assertIn(b"5", data)

    @unittest.skipUnless(os.name == "nt", "POSIX path normalization only applies on Windows")
    def test_normalizes_mnt_paths_in_stdout_stderr_and_output(self) -> None:
        tool = BashTool(timeout_s=5.0)
        with TemporaryDirectory() as td:
            root = Path(td)
            out = tool.run_sync(
                {"command": "printf '/mnt/c/Users/abc\\n'; printf '/mnt/c/Users/def\\n' >&2"},
                ToolContext(cwd=str(root), project_dir=str(root)),
            )

            self.assertIn("C:\\Users\\abc", out["stdout"])
            self.assertIn("C:\\Users\\def", out["stderr"])
            self.assertIn("C:\\Users\\abc", out["output"])
            self.assertIn("C:\\Users\\def", out["output"])


if __name__ == "__main__":
    unittest.main()

