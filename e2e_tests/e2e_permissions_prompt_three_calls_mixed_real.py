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


class TestE2EPermissionsPromptThreeCallsMixedReal(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mixed_deny_allow_across_three_calls(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"MIX3_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            injected = False

            async def inject_three_reads(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_three_reads",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(tool_use_id="call-1", name="Read", arguments={"file_path": "./a.txt"}),
                            ToolCall(tool_use_id="call-2", name="Read", arguments={"file_path": "./a.txt"}),
                            ToolCall(tool_use_id="call-3", name="Read", arguments={"file_path": "./a.txt"}),
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            answers = iter(["no", "yes", "yes"])

            async def answer_seq(_q: Any) -> str:
                try:
                    return next(answers)
                except StopIteration:
                    return "no"

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-three-reads", tool_name_pattern="*", hook=inject_three_reads)])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_seq)
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=10)

            r = await openagentic_sdk.run(prompt="Read three times.", options=opts)

            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(denied)
            self.assertEqual(getattr(denied[-1], "error_type", None), "PermissionDenied")

            ok2 = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-2"
                and getattr(e, "is_error", False) is False
            ]
            ok3 = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-3"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(ok2)
            self.assertTrue(ok3)


if __name__ == "__main__":
    unittest.main()

