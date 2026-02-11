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


class TestE2EToolsGlobGrepFindTokenReal(unittest.IsolatedAsyncioTestCase):
    async def test_glob_and_grep_can_find_token_without_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"GG_TOKEN_{uuid.uuid4().hex}"
            (root / "a.txt").write_text("nope\n", encoding="utf-8")
            (root / "b.txt").write_text(f"found:{token}\n", encoding="utf-8")
            (root / "c.md").write_text(f"found:{token}\n", encoding="utf-8")

            injected = False

            async def inject_tool_calls(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                return HookDecision(
                    action="inject_glob_grep",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-glob-1",
                                name="Glob",
                                arguments={"pattern": "*.txt", "root": "."},
                            ),
                            ToolCall(
                                tool_use_id="call-grep-1",
                                name="Grep",
                                arguments={"root": ".", "file_glob": "*.txt", "query": r"^found:", "mode": "content"},
                            ),
                        ],
                        usage=usage if isinstance(usage, dict) else None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-glob-grep", tool_name_pattern="*", hook=inject_tool_calls)])
            opts0 = make_options(root, allowed_tools=["Glob", "Grep"])
            opts = replace(opts0, hooks=hooks, max_steps=10)
            prompt = "Run the requested tools, then reply with exactly: GLOB_GREP_OK."

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            tool_uses = [e for e in events if getattr(e, "type", None) == "tool.use"]
            self.assertTrue(tool_uses)
            self.assertFalse(any(getattr(e, "name", None) == "Read" for e in tool_uses))

            grep_outs = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call-grep-1"
            ]
            if not grep_outs:
                self.fail(f"missing grep tool.result. tool_uses={[getattr(e,'name',None) for e in tool_uses]!r}")
            out = grep_outs[-1]
            if not isinstance(out, dict):
                self.fail(f"expected grep output dict, got {type(out)}: {out!r}")
            matches = out.get("matches", [])
            if not isinstance(matches, list):
                self.fail(f"expected grep.matches list, got {type(matches)}: {matches!r}")
            hit_lines = [m.get("text") for m in matches if isinstance(m, dict)]
            if not any(isinstance(t, str) and token in t for t in hit_lines):
                self.fail(f"expected grep output to include token. token={token!r} hit_lines={hit_lines!r}")


if __name__ == "__main__":
    unittest.main()
