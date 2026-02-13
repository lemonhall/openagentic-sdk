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


class TestE2EToolLoopRecoverReadMissingRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_read_missing_then_write_then_read_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"RECOVER_TOKEN_{uuid.uuid4().hex}"
            p = root / "missing.txt"

            stage = 0

            async def inject_missing_read_then_write_then_read(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read_missing",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./missing.txt"})],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_write",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-1",
                                    name="Write",
                                    arguments={"file_path": "./missing.txt", "content": token, "overwrite": True},
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
                        action="inject_read_after_write",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-2", name="Read", arguments={"file_path": "./missing.txt"})],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 3:
                    stage = 4
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="RECOVER_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject-recover", tool_name_pattern="*", hook=inject_missing_read_then_write_then_read)]
            )
            opts0 = make_options(root, allowed_tools=["Read", "Write"], hooks=hooks)
            opts = replace(opts0, max_steps=10)

            r = await openagentic_sdk.run(prompt="Run injected recover flow.", options=opts)

            saw_read_error = any(
                getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) != "PermissionDenied"
                for e in r.events
            )
            self.assertTrue(saw_read_error)

            saw_write_ok = any(
                getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-1"
                and getattr(e, "is_error", True) is False
                for e in r.events
            )
            self.assertTrue(saw_write_ok)

            self.assertTrue(p.exists())
            text = p.read_text(encoding="utf-8", errors="replace")
            self.assertIn(token, text)
            self.assertEqual((r.final_text or "").strip(), "RECOVER_OK")


if __name__ == "__main__":
    unittest.main()

