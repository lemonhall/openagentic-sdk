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
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2EPermissionsAcceptEditsReadPromptsEditAutoAllowsReal(unittest.IsolatedAsyncioTestCase):
    async def test_accept_edits_prompts_for_read_but_not_for_edit(self) -> None:
        async def answer_yes(_q: Any) -> str:
            return "yes"

        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ACCEPT_{uuid.uuid4().hex}"
            p = root / "a.txt"
            p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")

            injected = False

            async def inject_read_and_edit(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_read_edit",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"}),
                            ToolCall(
                                tool_use_id="call-edit-1",
                                name="Edit",
                                arguments={"file_path": "./a.txt", "old": "PLACEHOLDER", "new": token, "count": 1},
                            ),
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read-edit", tool_name_pattern="*", hook=inject_read_and_edit)])
            gate = PermissionGate(permission_mode="acceptEdits", interactive=False, user_answerer=answer_yes)

            opts0 = make_options(root, allowed_tools=["Read", "Edit"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=8)

            r = await openagentic_sdk.run(prompt="Run injected tool calls.", options=opts)

            # Read should prompt (acceptEdits falls back to prompt for non-edit tools).
            questions = [e for e in r.events if getattr(e, "type", None) == "user.question"]
            self.assertTrue(questions)

            read_ok = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(read_ok)

            edit_ok = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-edit-1"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(edit_ok)
            self.assertIn(token, p.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()

