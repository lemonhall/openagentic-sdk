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

from e2e_tests._harness import make_options


class TestE2EHooks(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_hook_rewrites_read_target(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"HOOK_{uuid.uuid4().hex}"
            (root / "a.txt").write_text("A_" + uuid.uuid4().hex, encoding="utf-8")
            (root / "b.txt").write_text(token, encoding="utf-8")

            async def rewrite_read(payload: Mapping[str, Any]) -> HookDecision:
                tool_input = payload.get("tool_input")
                if not isinstance(tool_input, dict):
                    return HookDecision()
                fp = tool_input.get("file_path")
                if isinstance(fp, str) and not fp.strip():
                    fp = None
                if fp is None:
                    fp = tool_input.get("filePath")
                if not isinstance(fp, str) or not fp.endswith("a.txt"):
                    return HookDecision()
                updated = dict(tool_input)
                updated["file_path"] = "./b.txt"
                return HookDecision(override_tool_input=updated)

            hooks = HookEngine(
                pre_tool_use=[HookMatcher(name="rewrite-a-to-b", tool_name_pattern="Read", hook=rewrite_read)]
            )

            opts0 = make_options(root, allowed_tools=["Read"])
            opts = replace(opts0, hooks=hooks)
            prompt = "Use the Read tool to read a.txt and reply with exactly the file content. Do not guess."

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            final_texts = [getattr(e, "final_text", "") for e in events if getattr(e, "type", None) == "result"]
            final_text = final_texts[-1] if final_texts else ""
            self.assertIn(token, final_text)


if __name__ == "__main__":
    unittest.main()
