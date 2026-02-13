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


class TestE2EToolsListIgnoresJunkDirsRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_list_skips_common_junk_dirs(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "keep.txt").write_text("ok\n", encoding="utf-8")

            (root / "node_modules").mkdir(parents=True, exist_ok=True)
            (root / "node_modules" / "secret.txt").write_text("no\n", encoding="utf-8")

            (root / ".git").mkdir(parents=True, exist_ok=True)
            (root / ".git" / "config").write_text("no\n", encoding="utf-8")

            (root / "__pycache__").mkdir(parents=True, exist_ok=True)
            (root / "__pycache__" / "x.pyc").write_text("no\n", encoding="utf-8")

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
                            assistant_text="LIST_IGNORE_OK",
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

            r = await openagentic_sdk.run(prompt="Run injected List for ignore test.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "LIST_IGNORE_OK")

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
            tree = out.get("output")
            self.assertIsInstance(tree, str)

            self.assertIn("keep.txt", tree)
            for banned in ("node_modules", ".git", "__pycache__", "secret.txt", "config", "x.pyc"):
                self.assertNotIn(banned, tree)


if __name__ == "__main__":
    unittest.main()

