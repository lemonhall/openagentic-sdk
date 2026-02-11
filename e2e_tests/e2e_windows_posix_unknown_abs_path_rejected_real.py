from __future__ import annotations

import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


@unittest.skipUnless(os.name == "nt", "Windows-only security test")
class TestE2EWindowsPosixUnknownAbsPathRejectedReal(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_posix_abs_path_is_rejected(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            injected = False

            async def inject_unknown_posix_path(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                return HookDecision(
                    action="inject_unknown_posix",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-read-posix-unknown",
                                name="Read",
                                arguments={"file_path": "", "filePath": "/etc/hosts"},
                            )
                        ],
                        usage=None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-unknown-posix", tool_name_pattern="*", hook=inject_unknown_posix_path)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="Read /etc/hosts", options=opts)
            err = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-posix-unknown"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(err)


if __name__ == "__main__":
    unittest.main()

