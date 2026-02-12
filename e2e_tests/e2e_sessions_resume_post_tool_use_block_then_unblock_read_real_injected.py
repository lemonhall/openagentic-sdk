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


class TestE2ESessionsResumePostToolUseBlockThenUnblockReadRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_resume_after_post_tool_use_block_can_read_when_unblocked(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"UNBLOCK_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token + "\n", encoding="utf-8")

            def _inject_read_then_finish(tool_use_id: str, final_text: str) -> HookEngine:
                stage = 0

                async def inject(payload: Mapping[str, Any]) -> HookDecision:
                    nonlocal stage
                    out = payload.get("output")
                    rid = getattr(out, "response_id", None) if out is not None else None
                    usage = getattr(out, "usage", None) if out is not None else None
                    pm = getattr(out, "provider_metadata", None) if out is not None else None

                    if stage == 0:
                        stage = 1
                        return HookDecision(
                            action="inject_read",
                            override_tool_output=ModelOutput(
                                assistant_text=None,
                                tool_calls=[ToolCall(tool_use_id=tool_use_id, name="Read", arguments={"file_path": "./a.txt"})],
                                usage=usage if isinstance(usage, dict) else None,
                                response_id=rid if isinstance(rid, str) else None,
                                provider_metadata=pm if isinstance(pm, dict) else None,
                            ),
                        )
                    if stage == 1:
                        stage = 2
                        return HookDecision(
                            action="inject_final",
                            override_tool_output=ModelOutput(
                                assistant_text=final_text,
                                tool_calls=[],
                                usage=usage if isinstance(usage, dict) else None,
                                response_id=rid if isinstance(rid, str) else None,
                                provider_metadata=pm if isinstance(pm, dict) else None,
                            ),
                        )
                    return HookDecision()

                return HookEngine(after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject)])

            async def post_block_read(payload: Mapping[str, Any]) -> HookDecision:
                if payload.get("tool_name") == "Read":
                    return HookDecision(block=True, block_reason="blocked for resume test", action="block")
                return HookDecision()

            opts0 = make_options(root, allowed_tools=["Read"])

            # Run 1: block.
            hooks1 = HookEngine(
                after_model_call=_inject_read_then_finish("call-read-1", "TURN1_OK").after_model_call,
                post_tool_use=[HookMatcher(name="post-block-read", tool_name_pattern="Read", hook=post_block_read)],
            )
            opts1 = replace(opts0, resume=session_id, hooks=hooks1, max_steps=8)
            r1 = await openagentic_sdk.run(prompt="Run1: Read is blocked by post tool hook.", options=opts1)
            self.assertEqual((r1.final_text or "").strip(), "TURN1_OK")
            blocked = [
                e
                for e in r1.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(blocked)

            events_path = root / "sessions" / session_id / "events.jsonl"
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            # Run 2: unblock (no post hook).
            hooks2 = _inject_read_then_finish("call-read-2", "TURN2_OK")
            opts2 = replace(opts0, resume=session_id, hooks=hooks2, max_steps=8)
            r2 = await openagentic_sdk.run(prompt="Run2: Read should succeed when unblocked.", options=opts2)
            self.assertEqual((r2.final_text or "").strip(), "TURN2_OK")
            ok = [
                e
                for e in r2.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-2"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(ok)
            out = getattr(ok[-1], "output", None)
            self.assertIsInstance(out, dict)
            self.assertIn(token, str(out.get("content") or ""))

            after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
            self.assertGreater(after_lines, before_lines)
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn('"tool_use_id":"call-read-1"', text)
            self.assertIn('"tool_use_id":"call-read-2"', text)


if __name__ == "__main__":
    unittest.main()

