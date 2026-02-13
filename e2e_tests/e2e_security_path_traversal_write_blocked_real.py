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


class TestE2ESecurityPathTraversalWriteBlockedReal(unittest.IsolatedAsyncioTestCase):
    async def test_write_blocks_parent_directory_escape(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"EVIL_{uuid.uuid4().hex}"
            evil_name = f"evil_{uuid.uuid4().hex}.txt"
            evil = root.parent / evil_name
            if evil.exists():
                evil.unlink()

            stage = 0

            async def inject_escape_write_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_escape_write",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-evil",
                                    name="Write",
                                    arguments={"file_path": f"../{evil_name}", "content": token, "overwrite": True},
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
                            assistant_text="ESCAPE_WRITE_OK",
                            tool_calls=[],
                            usage=None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-escape-write", tool_name_pattern="*", hook=inject_escape_write_then_finish)])
            opts0 = make_options(root, allowed_tools=["Write"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="Try to write ../evil.txt", options=opts)
            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-evil"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(denied)
            self.assertFalse(evil.exists())
            self.assertNotIn(token, r.final_text or "")


if __name__ == "__main__":
    unittest.main()
