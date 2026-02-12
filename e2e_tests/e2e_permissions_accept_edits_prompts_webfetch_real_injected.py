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


class TestE2EPermissionsAcceptEditsPromptsWebFetchRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_accept_edits_prompts_for_non_edit_tool_and_denies(self) -> None:
        answers = iter(["no"])

        async def answer_no(_q: Any) -> str:
            try:
                return next(answers)
            except StopIteration:
                return "no"

        with TemporaryDirectory() as td:
            root = Path(td)
            stage = 0

            async def inject_webfetch_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_webfetch",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-webfetch-1",
                                    name="WebFetch",
                                    arguments={"url": "https://example.com/"},
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
                            assistant_text="ACCEPT_EDITS_WEBFETCH_DENY_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-webfetch", tool_name_pattern="*", hook=inject_webfetch_then_finish)])
            gate = PermissionGate(permission_mode="acceptEdits", interactive=False, user_answerer=answer_no)
            opts0 = make_options(root, allowed_tools=["WebFetch"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=8)

            r = await openagentic_sdk.run(prompt="acceptEdits should prompt+deny WebFetch.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "ACCEPT_EDITS_WEBFETCH_DENY_OK")

            questions = [e for e in r.events if getattr(e, "type", None) == "user.question"]
            self.assertGreaterEqual(len(questions), 1)

            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-webfetch-1"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "PermissionDenied"
            ]
            self.assertTrue(denied)

            # No actual fetch result should be present because the tool is denied.
            outputs = [getattr(e, "output", None) for e in r.events if getattr(e, "type", None) == "tool.result"]
            self.assertFalse(any(isinstance(o, dict) and ("status" in o or "text" in o) for o in outputs))


if __name__ == "__main__":
    unittest.main()

