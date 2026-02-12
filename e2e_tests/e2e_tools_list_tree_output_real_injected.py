from __future__ import annotations

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


class TestE2EToolsListTreeOutputRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_list_emits_tree_output_with_expected_entries(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            (root / "sub").mkdir(parents=True, exist_ok=True)
            (root / "sub" / "b.md").write_text("b\n", encoding="utf-8")
            (root / "sub" / "nested").mkdir(parents=True, exist_ok=True)
            (root / "sub" / "nested" / "c.py").write_text("c\n", encoding="utf-8")

            stage = 0

            async def inject_list_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_list",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-list-1", name="List", arguments={"path": "."})],
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
                            assistant_text="LIST_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-list", tool_name_pattern="*", hook=inject_list_then_finish)])
            opts0 = make_options(root, allowed_tools=["List"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="Run injected List, then finish.", options=opts)

            self.assertEqual((r.final_text or "").strip(), "LIST_OK")
            uses = [e for e in r.events if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "List"]
            self.assertTrue(uses)

            results = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-list-1"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(results)
            out = getattr(results[-1], "output", None)
            self.assertIsInstance(out, dict)
            self.assertIn("output", out)
            self.assertIn("path", out)
            self.assertIn("count", out)

            tree = out.get("output")
            self.assertIsInstance(tree, str)
            for needle in ("a.txt", "sub/", "b.md", "nested/", "c.py"):
                self.assertIn(needle, tree)


if __name__ == "__main__":
    unittest.main()

