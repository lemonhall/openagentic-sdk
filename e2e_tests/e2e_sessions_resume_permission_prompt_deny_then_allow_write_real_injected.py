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


class TestE2ESessionsResumePermissionPromptDenyThenAllowWriteRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_resume_prompt_permission_denies_then_allows_write(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"RESUME_PROMPT_{uuid.uuid4().hex}"
            p = root / "a.txt"

            async def answer_no(_q: Any) -> str:
                return "no"

            async def answer_yes(_q: Any) -> str:
                return "yes"

            def _hooks_for_write(tool_use_id: str, final_text: str) -> HookEngine:
                stage = 0

                async def inject_write_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                    nonlocal stage
                    out = payload.get("output")
                    rid = getattr(out, "response_id", None) if out is not None else None
                    usage = getattr(out, "usage", None) if out is not None else None
                    pm = getattr(out, "provider_metadata", None) if out is not None else None

                    if stage == 0:
                        stage = 1
                        return HookDecision(
                            action="inject_write",
                            override_tool_output=ModelOutput(
                                assistant_text=None,
                                tool_calls=[
                                    ToolCall(
                                        tool_use_id=tool_use_id,
                                        name="Write",
                                        arguments={"file_path": "./a.txt", "content": token, "overwrite": True},
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
                                assistant_text=final_text,
                                tool_calls=[],
                                usage=usage if isinstance(usage, dict) else None,
                                response_id=rid if isinstance(rid, str) else None,
                                provider_metadata=pm if isinstance(pm, dict) else None,
                            ),
                        )

                    return HookDecision()

                return HookEngine(
                    after_model_call=[HookMatcher(name="inject-write", tool_name_pattern="*", hook=inject_write_then_finish)]
                )

            # Run 1: deny.
            gate1 = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_no)
            opts0 = make_options(root, allowed_tools=["Write"])
            opts1 = replace(opts0, resume=session_id, permission_gate=gate1, hooks=_hooks_for_write("call-write-1", "TURN1_OK"), max_steps=8)
            r1 = await openagentic_sdk.run(prompt="Run1: injected write should be denied by prompt permission.", options=opts1)
            self.assertEqual((r1.final_text or "").strip(), "TURN1_OK")

            q1 = [e for e in r1.events if getattr(e, "type", None) == "user.question"]
            self.assertGreaterEqual(len(q1), 1)
            denied = [
                e
                for e in r1.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-1"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "PermissionDenied"
            ]
            self.assertTrue(denied)
            self.assertFalse(p.exists(), "denied write must not create the file")

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            # Run 2: allow (same session).
            gate2 = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_yes)
            opts2 = replace(opts0, resume=session_id, permission_gate=gate2, hooks=_hooks_for_write("call-write-2", "TURN2_OK"), max_steps=8)
            r2 = await openagentic_sdk.run(prompt="Run2: injected write should be allowed by prompt permission.", options=opts2)
            self.assertEqual((r2.final_text or "").strip(), "TURN2_OK")

            q2 = [e for e in r2.events if getattr(e, "type", None) == "user.question"]
            self.assertGreaterEqual(len(q2), 1)
            allowed = [
                e
                for e in r2.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-2"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(allowed)
            self.assertTrue(p.exists())
            self.assertIn(token, p.read_text(encoding="utf-8", errors="replace"))

            after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
            self.assertGreater(after_lines, before_lines)
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn('"type":"user.question"', text)
            self.assertIn('"error_type":"PermissionDenied"', text)


if __name__ == "__main__":
    unittest.main()

