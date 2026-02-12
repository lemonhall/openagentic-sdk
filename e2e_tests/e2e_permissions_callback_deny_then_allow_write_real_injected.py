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


class TestE2EPermissionsCallbackDenyThenAllowWriteRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_callback_gate_denies_then_allows_write(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "a.txt"
            token = f"CALLBACK_WRITE_{uuid.uuid4().hex}"

            stage = 0
            approvals = 0

            async def approve_write_only(_tool_name: str, _tool_input: Mapping[str, Any], _ctx: Mapping[str, Any]) -> bool:
                nonlocal approvals
                approvals += 1
                return approvals >= 2

            async def inject_two_writes_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_write_1",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-1",
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
                        action="inject_write_2",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-2",
                                    name="Write",
                                    arguments={"file_path": "./a.txt", "content": token, "overwrite": True},
                                )
                            ],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 2:
                    stage = 3
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="CALLBACK_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-writes", tool_name_pattern="*", hook=inject_two_writes_then_finish)])
            gate = PermissionGate(permission_mode="callback", approver=approve_write_only)
            opts0 = make_options(root, allowed_tools=["Write"], hooks=hooks)
            opts = replace(opts0, permission_gate=gate, max_steps=8)

            r = await openagentic_sdk.run(prompt="Run callback deny/allow write flow.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "CALLBACK_OK")

            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-1"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "PermissionDenied"
            ]
            self.assertTrue(denied)

            allowed = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-2"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(allowed)

            self.assertTrue(p.exists())
            self.assertIn(token, p.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()

