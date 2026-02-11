from __future__ import annotations

import unittest
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


class TestE2ERuntimePermissionPromptDeniesReal(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_emits_user_question_then_permission_denied(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "fixture.txt").write_text("hello", encoding="utf-8")

            stage = 0

            async def inject_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read_prompt",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-read-1",
                                    name="Read",
                                    arguments={"file_path": "./fixture.txt"},
                                )
                            ],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="PROMPT_DENY_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read-prompt", tool_name_pattern="*", hook=inject_read_then_finish)])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=None)

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./fixture.txt", options=opts):
                events.append(ev)

            questions = [e for e in events if getattr(e, "type", None) == "user.question"]
            self.assertTrue(questions)

            denied = [
                e
                for e in events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(denied)
            self.assertEqual(getattr(denied[-1], "error_type", None), "PermissionDenied")


if __name__ == "__main__":
    unittest.main()

