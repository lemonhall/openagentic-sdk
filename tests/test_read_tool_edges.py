import base64
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.read import ReadTool


_ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO3Z0p8AAAAASUVORK5CYII="
)


class TestReadToolEdges(unittest.TestCase):
    def test_image_mode_returns_base64_and_mime_type(self) -> None:
        tool = ReadTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "x.png"
            p.write_bytes(_ONE_BY_ONE_PNG)

            out = tool.run_sync({"file_path": str(p)}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["mime_type"], "image/png")
            self.assertEqual(base64.b64decode(out["image"]), _ONE_BY_ONE_PNG)

    def test_fbs_treated_as_text(self) -> None:
        tool = ReadTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "schema.fbs"
            p.write_text("table Monster { hp:int; }\n", encoding="utf-8")

            out = tool.run_sync({"file_path": str(p)}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertIn("table Monster", out["content"])
            self.assertNotIn("image", out)

    def test_abs_outside_project_is_rejected(self) -> None:
        tool = ReadTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            project_root = root / "project"
            project_root.mkdir()
            outside = root / "outside.txt"
            outside.write_text("nope", encoding="utf-8")
            with self.assertRaises(ValueError):
                tool.run_sync({"file_path": str(outside)}, ToolContext(cwd=str(project_root), project_dir=str(project_root)))

    @unittest.skipUnless(os.name == "nt", "POSIX-like /mnt/... mapping only applies on Windows")
    def test_windows_mnt_data_path_maps_under_project_root(self) -> None:
        tool = ReadTool()
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("hello", encoding="utf-8")
            out = tool.run_sync({"file_path": "/mnt/data/a.txt"}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["content"], "hello")

    def test_truncated_flag_when_max_bytes_exceeded(self) -> None:
        tool = ReadTool(max_bytes=3)
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "big.txt"
            p.write_text("abcdef", encoding="utf-8")

            out = tool.run_sync({"file_path": str(p)}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["content"], "abc")
            self.assertTrue(out["truncated"])


if __name__ == "__main__":
    unittest.main()
