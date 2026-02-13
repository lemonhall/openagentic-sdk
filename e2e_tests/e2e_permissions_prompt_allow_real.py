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


class TestE2EPermissionsPromptAllowReal(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_allow_emits_user_question_and_runs_tool(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PUBLIC_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            injected = False

            async def inject_read(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_read",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            async def answer_yes(_q: Any) -> str:
                return "yes"

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read)])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_yes)

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./a.txt", options=opts):
                events.append(ev)

            self.assertTrue(any(getattr(e, "type", None) == "user.question" for e in events))
            ok = [
                e
                for e in events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()

