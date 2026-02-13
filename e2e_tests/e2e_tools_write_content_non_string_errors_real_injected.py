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


class TestE2EToolsWriteContentNonStringErrorsRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_write_rejects_non_string_content_then_valid_write_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"WRITE_OK_{uuid.uuid4().hex}"

            stage = 0

            async def inject_write_bad_then_good_then_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_write_bad",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-bad",
                                    name="Write",
                                    arguments={"file_path": "./a.txt", "content": 123, "overwrite": True},
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
                        action="inject_read_missing",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-read-missing",
                                    name="Read",
                                    arguments={"file_path": "./a.txt"},
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
                        action="inject_write_good",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-write-good",
                                    name="Write",
                                    arguments={"file_path": "./a.txt", "content": token, "overwrite": True},
                                )
                            ],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 3:
                    stage = 4
                    return HookDecision(
                        action="inject_read_after_write",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-after", name="Read", arguments={"file_path": "./a.txt"})],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 4:
                    stage = 5
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="WRITE_TYPE_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject-write", tool_name_pattern="*", hook=inject_write_bad_then_good_then_read_then_finish)]
            )
            opts0 = make_options(root, allowed_tools=["Write", "Read"], hooks=hooks)
            opts = replace(opts0, max_steps=14)

            r = await openagentic_sdk.run(prompt="Run injected Write(content type) then Read.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "WRITE_TYPE_OK")

            bad = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-bad"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "ValueError"
            ]
            self.assertTrue(bad)

            missing = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-missing"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", None) == "FileNotFoundError"
            ]
            self.assertTrue(missing, "after invalid Write, file should still be missing")

            good = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-write-good"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(good)

            ok_read = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-after"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(ok_read)
            out = getattr(ok_read[-1], "output", None)
            self.assertIsInstance(out, dict)
            self.assertIn(token, str(out.get("content") or ""))


if __name__ == "__main__":
    unittest.main()
