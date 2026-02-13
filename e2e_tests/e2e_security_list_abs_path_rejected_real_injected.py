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


class TestE2ESecurityListAbsPathRejectedRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_list_abs_path_outside_project_is_rejected(self) -> None:
        with TemporaryDirectory() as td_outside:
            outside_dir = Path(td_outside)
            outside_token = f"OUTSIDE_LIST_{uuid.uuid4().hex}"
            (outside_dir / f"{outside_token}.txt").write_text("x\n", encoding="utf-8")

            with TemporaryDirectory() as td:
                root = Path(td)

                stage = 0

                async def inject_list_outside_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                    nonlocal stage
                    out = payload.get("output")
                    rid = getattr(out, "response_id", None) if out is not None else None
                    usage = getattr(out, "usage", None) if out is not None else None
                    pm = getattr(out, "provider_metadata", None) if out is not None else None

                    if stage == 0:
                        stage = 1
                        return HookDecision(
                            action="inject_list_outside",
                            override_tool_output=ModelOutput(
                                assistant_text=None,
                                tool_calls=[
                                    ToolCall(tool_use_id="call-list-1", name="List", arguments={"path": str(outside_dir)})
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
                                assistant_text="LIST_DENIED_OK",
                                tool_calls=[],
                                usage=usage if isinstance(usage, dict) else None,
                                response_id=rid if isinstance(rid, str) else None,
                                provider_metadata=pm if isinstance(pm, dict) else None,
                            ),
                        )

                    return HookDecision()

                hooks = HookEngine(
                    after_model_call=[
                        HookMatcher(name="inject-list-outside", tool_name_pattern="*", hook=inject_list_outside_then_finish)
                    ]
                )
                opts0 = make_options(root, allowed_tools=["List"], hooks=hooks)
                opts = replace(opts0, max_steps=6)

                r = await openagentic_sdk.run(prompt="Attempt injected List outside project.", options=opts)
                self.assertEqual((r.final_text or "").strip(), "LIST_DENIED_OK")

                denied = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "tool_use_id", None) == "call-list-1"
                    and getattr(e, "is_error", False) is True
                ]
                self.assertTrue(denied)
                self.assertIn(getattr(denied[-1], "error_type", ""), ("ValueError", "PermissionDenied"))

                # Ensure no outside token leaks via outputs/final text (defense-in-depth).
                self.assertNotIn(outside_token, r.final_text or "")
                out_text = "\n".join(str(getattr(e, "output", "") or "") for e in r.events if getattr(e, "type", None) == "tool.result")
                self.assertNotIn(outside_token, out_text)


if __name__ == "__main__":
    unittest.main()

