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


class TestE2EPermissionsPromptDenyThenAllowReal(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_denies_first_call_allows_second_call(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ALLOW_TOKEN_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            injected = False

            async def inject_two_reads_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_two_reads",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(tool_use_id="call-read-deny", name="Read", arguments={"file_path": "./a.txt"}),
                            ToolCall(tool_use_id="call-read-allow", name="Read", arguments={"file_path": "./a.txt"}),
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            answers = iter(["no", "yes"])

            async def answer_mixed(_q: Any) -> str:
                try:
                    return next(answers)
                except StopIteration:
                    return "no"

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-two-reads", tool_name_pattern="*", hook=inject_two_reads_then_finish)])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_mixed)

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="Read ./a.txt twice.", options=opts)

            questions = [e for e in r.events if getattr(e, "type", None) == "user.question"]
            self.assertGreaterEqual(len(questions), 2)

            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-deny"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(denied)
            self.assertEqual(getattr(denied[-1], "error_type", None), "PermissionDenied")

            allowed = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-allow"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(allowed)
            self.assertIn(token, str(getattr(allowed[-1], "output", "") or ""))


if __name__ == "__main__":
    unittest.main()

