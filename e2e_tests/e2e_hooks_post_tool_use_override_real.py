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


class TestE2EHooksPostToolUseOverrideReal(unittest.IsolatedAsyncioTestCase):
    async def test_post_tool_use_can_override_read_output(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            original = f"ORIGINAL_{uuid.uuid4().hex}"
            overridden = f"OVERRIDDEN_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(original, encoding="utf-8")

            injected = False

            async def inject_read(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True

                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                return HookDecision(
                    action="inject_read",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-read-1",
                                name="Read",
                                arguments={"file_path": "./a.txt"},
                            )
                        ],
                        usage=usage if isinstance(usage, dict) else None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            async def override_read_output(payload: Mapping[str, Any]) -> HookDecision:
                tool_output = payload.get("tool_output")
                if not isinstance(tool_output, dict):
                    return HookDecision()
                if payload.get("tool_name") != "Read":
                    return HookDecision()
                updated = dict(tool_output)
                updated["content"] = overridden
                return HookDecision(action="override_read_output", override_tool_output=updated)

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read)],
                post_tool_use=[HookMatcher(name="override-read-output", tool_name_pattern="Read", hook=override_read_output)],
            )

            opts0 = make_options(root, allowed_tools=["Read"])
            opts = replace(opts0, hooks=hooks, max_steps=10)
            prompt = "Use the Read tool to read ./a.txt and reply with exactly the file content. Do not guess."

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            read_results = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", "") == "call-read-1"
            ]
            self.assertTrue(read_results)
            out = read_results[-1]
            self.assertIsInstance(out, dict)
            self.assertIn(overridden, str(out.get("content") or ""))
            self.assertNotIn(original, str(out.get("content") or ""))

            final_texts = [getattr(e, "final_text", "") for e in events if getattr(e, "type", None) == "result"]
            self.assertTrue(final_texts)
            self.assertIn(overridden, final_texts[-1])


if __name__ == "__main__":
    unittest.main()
