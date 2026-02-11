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


class TestE2ESecurityPathTraversalReadBlockedReal(unittest.IsolatedAsyncioTestCase):
    async def test_read_blocks_parent_directory_escape(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ESCAPE_{uuid.uuid4().hex}"
            escape_name = f"escape_{uuid.uuid4().hex}.txt"
            escape = root.parent / escape_name
            escape.write_text(token, encoding="utf-8")

            stage = 0

            async def inject_escape_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_escape_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-read-escape",
                                    name="Read",
                                    arguments={"file_path": f"../{escape_name}"},
                                )
                            ],
                            usage=None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final",
                        override_tool_output=ModelOutput(
                            assistant_text="ESCAPE_READ_OK",
                            tool_calls=[],
                            usage=None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-escape-read", tool_name_pattern="*", hook=inject_escape_read_then_finish)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="Try to read ../escape.txt", options=opts)
            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-escape"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(denied)
            self.assertNotIn(token, str(getattr(denied[-1], "output", "") or ""))
            self.assertNotIn(token, r.final_text or "")
            if escape.exists():
                escape.unlink()


if __name__ == "__main__":
    unittest.main()
