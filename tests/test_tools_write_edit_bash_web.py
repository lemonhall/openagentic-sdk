import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.bash import BashTool
from openagentic_sdk.tools.edit import EditTool
from openagentic_sdk.tools.web_fetch import WebFetchTool
from openagentic_sdk.tools.web_search_tavily import WebSearchTool
from openagentic_sdk.tools.write import WriteTool


class TestMoreTools(unittest.TestCase):
    def test_write_creates_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            tool = WriteTool()
            out = tool.run_sync({"file_path": "a.txt", "content": "hi", "overwrite": False}, ToolContext(cwd=str(root)))
            self.assertTrue((root / "a.txt").exists())
            self.assertEqual(out["bytes_written"], 2)

    def test_edit_replaces_text(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "a.txt"
            p.write_text("hello world", encoding="utf-8")
            tool = EditTool()
            out = tool.run_sync({"file_path": str(p), "old": "world", "new": "there", "count": 1}, ToolContext(cwd=str(root)))
            self.assertEqual(p.read_text(encoding="utf-8"), "hello there")
            self.assertEqual(out["replacements"], 1)

    def test_bash_runs_command(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            tool = BashTool(timeout_s=5.0)
            out = tool.run_sync({"command": "echo hello"}, ToolContext(cwd=str(root)))
            self.assertEqual(out["exit_code"], 0)
            self.assertIn("hello", out["stdout"])

    def test_bash_errors_when_no_shell_available(self) -> None:
        old_path = os.environ.get("PATH")
        os.environ["PATH"] = ""
        try:
            tool = BashTool(timeout_s=1.0)
            with self.assertRaises(RuntimeError):
                tool.run_sync({"command": "echo hello"}, ToolContext(cwd="/"))
        finally:
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path

    def test_web_fetch_uses_extract_transport(self) -> None:
        os.environ["TAVILY_API_KEY"] = "test"

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            return {"results": [{"url": "https://example.com", "raw_content": "ok"}]}

        tool = WebFetchTool(extract_transport=extract_transport, allow_private_networks=True)
        out = tool.run_sync({"url": "https://example.com"}, ToolContext(cwd="/"))
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["text"], "ok")
        self.assertEqual(out["backend"], "tavily_extract")

    def test_web_search_tavily_uses_transport(self) -> None:
        os.environ["TAVILY_API_KEY"] = "test"

        def transport(url, headers, payload):
            return {"results": [{"title": "t", "url": "u", "content": "c"}]}

        tool = WebSearchTool(transport=transport)
        out = tool.run_sync({"query": "x", "max_results": 5}, ToolContext(cwd="/"))
        self.assertEqual(out["results"][0]["source"], "tavily")


if __name__ == "__main__":
    unittest.main()
