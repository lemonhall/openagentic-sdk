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


class TestE2ESecurityAbsolutePathOutsideProjectRejectedReal(unittest.IsolatedAsyncioTestCase):
    async def test_read_absolute_path_outside_project_is_rejected(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ABS_ESCAPE_{uuid.uuid4().hex}"
            outside = root.parent / f"outside_{uuid.uuid4().hex}.txt"
            outside.write_text(token, encoding="utf-8")

            injected = False

            async def inject_abs_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_abs_read",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-read-abs-out",
                                name="Read",
                                arguments={"file_path": str(outside)},
                            )
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-abs-read", tool_name_pattern="*", hook=inject_abs_read_then_finish)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="Try to read an absolute path outside project.", options=opts)
            err = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-abs-out"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(err)
            self.assertNotIn(token, str(getattr(err[-1], "output", "") or ""))
            self.assertNotIn(token, r.final_text or "")
            if outside.exists():
                outside.unlink()


if __name__ == "__main__":
    unittest.main()

