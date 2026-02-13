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


class TestE2ERuntimeAllowedToolsGateToolNotAllowedRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_disallowed_tool_yields_tool_not_allowed_and_no_side_effects(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"READ_OK_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token + "\n", encoding="utf-8")
            forbidden = root / "forbidden.txt"

            stage = 0

            async def inject_disallowed_write_and_allowed_read(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_write_and_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-1",
                                    name="Write",
                                    arguments={"file_path": "./forbidden.txt", "content": "NOPE", "overwrite": True},
                                ),
                                ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"}),
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
                            assistant_text="GATE_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-allowed-tools-gate", tool_name_pattern="*", hook=inject_disallowed_write_and_allowed_read)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=8)

            r = await openagentic_sdk.run(prompt="Exercise allowed_tools gate.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "GATE_OK")

            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-1"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "ToolNotAllowed"
            ]
            self.assertTrue(denied)

            used_write = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Write" for e in r.events)
            self.assertFalse(used_write, "disallowed tools must be denied before tool.use is emitted")
            self.assertFalse(forbidden.exists(), "disallowed Write must not create files")

            ok_read = any(
                getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", True) is False
                for e in r.events
            )
            self.assertTrue(ok_read)


if __name__ == "__main__":
    unittest.main()

