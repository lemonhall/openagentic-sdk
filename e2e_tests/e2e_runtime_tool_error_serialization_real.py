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


class TestE2ERuntimeToolErrorSerializationReal(unittest.IsolatedAsyncioTestCase):
    async def test_tool_exception_is_serialized_as_tool_result(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"FIXTURE_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            stage = 0

            async def inject_bad_edit_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_bad_edit",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-edit-1",
                                    name="Edit",
                                    arguments={"file_path": "./a.txt", "old": "MISSING_OLD", "new": "X", "count": 1},
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
                            assistant_text="TOOL_ERROR_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-bad-edit", tool_name_pattern="*", hook=inject_bad_edit_then_finish)])
            opts0 = make_options(root, allowed_tools=["Edit"], hooks=hooks)
            opts = replace(opts0, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Edit ./a.txt", options=opts):
                events.append(ev)

            saw_tool_use = any(
                getattr(e, "type", None) == "tool.use" and getattr(e, "tool_use_id", None) == "call-edit-1" for e in events
            )
            self.assertTrue(saw_tool_use)

            errs = [
                e
                for e in events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-edit-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(errs)
            self.assertEqual(getattr(errs[-1], "error_type", None), "ValueError")
            self.assertIn("old", str(getattr(errs[-1], "error_message", "") or ""))


if __name__ == "__main__":
    unittest.main()

