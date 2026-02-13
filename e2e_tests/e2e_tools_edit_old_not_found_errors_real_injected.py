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


class TestE2EToolsEditOldNotFoundErrorsRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_edit_old_not_found_errors_and_file_unchanged(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            original = f"ORIG_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(original + "\n", encoding="utf-8")

            stage = 0

            async def inject_edit_then_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_edit_missing_old",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-edit-1",
                                    name="Edit",
                                    arguments={"file_path": "./a.txt", "old": "MISSING_OLD", "new": "NEW", "count": 1},
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
                        action="inject_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
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
                            assistant_text="EDIT_OLD_NOT_FOUND_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-edit", tool_name_pattern="*", hook=inject_edit_then_read_then_finish)])
            opts0 = make_options(root, allowed_tools=["Edit", "Read"], hooks=hooks)
            opts = replace(opts0, max_steps=10)

            r = await openagentic_sdk.run(prompt="Run injected Edit(old not found) then Read.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "EDIT_OLD_NOT_FOUND_OK")

            edit_err = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-edit-1"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "ValueError"
            ]
            self.assertTrue(edit_err)

            read_ok = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(read_ok)
            out = getattr(read_ok[-1], "output", None)
            self.assertIsInstance(out, dict)
            self.assertIn(original, str(out.get("content") or ""))


if __name__ == "__main__":
    unittest.main()

