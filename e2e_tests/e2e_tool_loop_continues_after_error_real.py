from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2EToolLoopContinuesAfterErrorReal(unittest.IsolatedAsyncioTestCase):
    async def test_second_tool_call_runs_even_if_first_errors(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"OK_{uuid.uuid4().hex}"
            (root / "ok.txt").write_text(token, encoding="utf-8")

            injected = False

            async def inject_bad_then_good_read(payload: Mapping[str, object]) -> HookDecision:
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
                            ToolCall(tool_use_id="call-read-missing", name="Read", arguments={"file_path": "./missing.txt"}),
                            ToolCall(tool_use_id="call-read-ok", name="Read", arguments={"file_path": "./ok.txt"}),
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-two-reads", tool_name_pattern="*", hook=inject_bad_then_good_read)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="Read a missing file then read ok.txt.", options=opts)

            missing = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-missing"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(missing)

            ok = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-ok"
                and getattr(e, "is_error", False) is False
            ]
            self.assertTrue(ok)
            self.assertIn(token, str(getattr(ok[-1], "output", "") or ""))


if __name__ == "__main__":
    unittest.main()

