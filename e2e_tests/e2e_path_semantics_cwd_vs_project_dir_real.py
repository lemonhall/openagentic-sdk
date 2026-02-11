from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2EPathSemanticsCwdVsProjectDirReal(unittest.IsolatedAsyncioTestCase):
    async def test_relative_paths_use_cwd_but_are_confined_to_project(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "sub"
            sub.mkdir()
            token = f"CWD_TOKEN_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            # Create an outside file to prove escape is blocked.
            escape_name = f"escape_{uuid.uuid4().hex}.txt"
            escape_path = root.parent / escape_name
            escape_path.write_text("SHOULD_NOT_READ", encoding="utf-8")

            injected = False

            async def inject_reads(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_reads",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(tool_use_id="call-in", name="Read", arguments={"file_path": "../a.txt"}),
                            ToolCall(tool_use_id="call-out", name="Read", arguments={"file_path": f"../../{escape_name}"}),
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-reads", tool_name_pattern="*", hook=inject_reads)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, cwd=str(sub), project_dir=str(root), max_steps=8)

            r = await openagentic_sdk.run(prompt="Injected reads.", options=opts)

            ok_in = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-in"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(ok_in)
            self.assertIn(token, str(getattr(ok_in[-1], "output", "") or ""))

            err_out = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-out"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(err_out)

            if escape_path.exists():
                escape_path.unlink()


if __name__ == "__main__":
    unittest.main()
