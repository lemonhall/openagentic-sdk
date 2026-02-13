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


class TestE2EToolsEditRoundtripReal(unittest.IsolatedAsyncioTestCase):
    async def test_edit_tool_changes_file_content(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"EDIT_TOKEN_{uuid.uuid4().hex}"
            p = root / "edit.txt"
            p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")

            injected = False

            async def inject_tool_calls(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                return HookDecision(
                    action="inject_edit_read",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-edit-1",
                                name="Edit",
                                arguments={"file_path": "./edit.txt", "old": "PLACEHOLDER", "new": token, "count": 1},
                            ),
                            ToolCall(
                                tool_use_id="call-read-1",
                                name="Read",
                                arguments={"file_path": "./edit.txt"},
                            ),
                        ],
                        usage=usage if isinstance(usage, dict) else None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-edit-read", tool_name_pattern="*", hook=inject_tool_calls)])

            opts0 = make_options(root, allowed_tools=["Edit", "Read"])
            opts = replace(opts0, hooks=hooks, max_steps=10)
            prompt = (
                "You are graded by whether the file content actually changes on disk.\n"
                "After you receive tool results, reply with exactly: EDIT_OK."
            )

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            text = p.read_text(encoding="utf-8", errors="replace")
            if token not in text:
                tool_uses = [getattr(e, "name", None) for e in events if getattr(e, "type", None) == "tool.use"]
                final_texts = [getattr(e, "final_text", "") for e in events if getattr(e, "type", None) == "result"]
                self.fail(f"expected edited file to include token. tools={tool_uses!r} final={final_texts[-1:]!r} text={text!r}")
            saw_edit = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in events)
            self.assertTrue(saw_edit)


if __name__ == "__main__":
    unittest.main()
