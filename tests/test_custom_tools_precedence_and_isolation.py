import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.custom_tools import discover_custom_tool_files, load_custom_tools


def _write_tool_module(path: Path, *, tool_name: str, where: str) -> None:
    path.write_text(
        f"""\
from dataclasses import dataclass
from typing import Any, Mapping

from openagentic_sdk.tools.base import Tool, ToolContext


@dataclass(frozen=True, slots=True)
class _T(Tool):
    name: str = {tool_name!r}
    description: str = "test tool"

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        _ = (tool_input, ctx)
        return {{"where": {where!r}}}


TOOL = _T()
""",
        encoding="utf-8",
    )


class TestCustomToolsPrecedenceAndIsolation(unittest.TestCase):
    def test_discovery_order_is_global_then_project_then_opencode(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            global_root = root / "global"
            os.environ["OPENCODE_CONFIG_DIR"] = str(global_root)
            try:
                (global_root / "tools").mkdir(parents=True)
                (root / "tools").mkdir(parents=True)
                (root / ".opencode" / "tools").mkdir(parents=True)

                p_global = global_root / "tools" / "hello_global.py"
                p_project = root / "tools" / "hello_project.py"
                p_opencode = root / ".opencode" / "tools" / "hello_opencode.py"
                _write_tool_module(p_global, tool_name="Hello", where="global")
                _write_tool_module(p_project, tool_name="Hello", where="project")
                _write_tool_module(p_opencode, tool_name="Hello", where="opencode")

                found = discover_custom_tool_files(project_dir=str(root))
                self.assertEqual(found, [p_global, p_project, p_opencode])
            finally:
                os.environ.pop("OPENCODE_CONFIG_DIR", None)

    def test_precedence_overrides_tool_registry_last_wins(self) -> None:
        from openagentic_sdk.tools.base import ToolContext
        from openagentic_sdk.tools.registry import ToolRegistry

        with TemporaryDirectory() as td:
            root = Path(td)
            global_root = root / "global"
            os.environ["OPENCODE_CONFIG_DIR"] = str(global_root)
            try:
                (global_root / "tools").mkdir(parents=True)
                (root / "tools").mkdir(parents=True)
                (root / ".opencode" / "tools").mkdir(parents=True)

                _write_tool_module(global_root / "tools" / "hello_global.py", tool_name="Hello", where="global")
                _write_tool_module(root / "tools" / "hello_project.py", tool_name="Hello", where="project")
                _write_tool_module(root / ".opencode" / "tools" / "hello_opencode.py", tool_name="Hello", where="opencode")

                reg = ToolRegistry(load_custom_tools(project_dir=str(root)))
                out = reg.get("Hello").run_sync({}, ToolContext(cwd=str(root), project_dir=str(root)))
                self.assertEqual(out["where"], "opencode")
            finally:
                os.environ.pop("OPENCODE_CONFIG_DIR", None)

    def test_import_error_is_isolated(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".opencode" / "tools").mkdir(parents=True)

            _write_tool_module(root / ".opencode" / "tools" / "good.py", tool_name="Good", where="ok")
            (root / ".opencode" / "tools" / "bad.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")

            tools = load_custom_tools(project_dir=str(root))
            names = sorted([t.name for t in tools])
            self.assertIn("Good", names)

    def test_tools_dir_overrides_tool_dir_within_same_root(self) -> None:
        from openagentic_sdk.tools.base import ToolContext
        from openagentic_sdk.tools.registry import ToolRegistry

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "tool").mkdir(parents=True)
            (root / "tools").mkdir(parents=True)

            _write_tool_module(root / "tool" / "x.py", tool_name="X", where="tool")
            _write_tool_module(root / "tools" / "x.py", tool_name="X", where="tools")

            reg = ToolRegistry(load_custom_tools(project_dir=str(root)))
            out = reg.get("X").run_sync({}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["where"], "tools")

    def test_opencode_tools_dir_overrides_opencode_tool_dir(self) -> None:
        from openagentic_sdk.tools.base import ToolContext
        from openagentic_sdk.tools.registry import ToolRegistry

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".opencode" / "tool").mkdir(parents=True)
            (root / ".opencode" / "tools").mkdir(parents=True)

            _write_tool_module(root / ".opencode" / "tool" / "y.py", tool_name="Y", where="tool")
            _write_tool_module(root / ".opencode" / "tools" / "y.py", tool_name="Y", where="tools")

            reg = ToolRegistry(load_custom_tools(project_dir=str(root)))
            out = reg.get("Y").run_sync({}, ToolContext(cwd=str(root), project_dir=str(root)))
            self.assertEqual(out["where"], "tools")


if __name__ == "__main__":
    unittest.main()
