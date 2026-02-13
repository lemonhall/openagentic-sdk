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


class TestE2EPermissionsDefaultSafeToolsNoPromptRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_default_mode_read_is_safe_and_does_not_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"SAFE_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token + "\n", encoding="utf-8")

            async def answerer_should_not_be_called(_q: Any) -> str:
                raise AssertionError("default safe tools must not prompt")

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
                        action="inject_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
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
                            assistant_text="SAFE_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read_then_finish)])
            gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=answerer_should_not_be_called)
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=8)

            r = await openagentic_sdk.run(prompt="Read is safe in default mode.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "SAFE_OK")
            self.assertFalse([e for e in r.events if getattr(e, "type", None) == "user.question"])

            ok = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()

