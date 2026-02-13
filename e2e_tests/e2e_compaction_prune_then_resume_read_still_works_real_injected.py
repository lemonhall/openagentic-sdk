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
from openagentic_sdk.options import CompactionOptions
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2ECompactionPruneThenResumeReadStillWorksRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_prune_old_tool_outputs_then_resume_can_still_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            big_token = f"BIG_{uuid.uuid4().hex}"
            small_token = f"SMALL_{uuid.uuid4().hex}"
            (root / "big.txt").write_text(("X" * 8000) + big_token + ("\n" + ("Y" * 8000)), encoding="utf-8")
            (root / "small.txt").write_text(small_token + "\n", encoding="utf-8")

            compaction = CompactionOptions(auto=False, prune=True, protect_tool_output_tokens=1, min_prune_tokens=1)

            def _inject_read_big_then_finish() -> HookEngine:
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
                            action="inject_read_big",
                            override_tool_output=ModelOutput(
                                assistant_text=None,
                                tool_calls=[ToolCall(tool_use_id="call-read-big", name="Read", arguments={"file_path": "./big.txt"})],
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
                                assistant_text="TURN1_OK",
                                tool_calls=[],
                                # Make compaction eligibility easy.
                                usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                                response_id=rid if isinstance(rid, str) else None,
                                provider_metadata=pm if isinstance(pm, dict) else None,
                            ),
                        )
                    return HookDecision()

                return HookEngine(after_model_call=[HookMatcher(name="inject-read-big", tool_name_pattern="*", hook=inject)])

            def _inject_final(text: str) -> HookEngine:
                injected = False

                async def inject(payload: Mapping[str, Any]) -> HookDecision:
                    nonlocal injected
                    if injected:
                        return HookDecision()
                    injected = True
                    out = payload.get("output")
                    rid = getattr(out, "response_id", None) if out is not None else None
                    usage = getattr(out, "usage", None) if out is not None else None
                    pm = getattr(out, "provider_metadata", None) if out is not None else None
                    return HookDecision(
                        action="inject_final",
                        override_tool_output=ModelOutput(
                            assistant_text=text,
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookEngine(after_model_call=[HookMatcher(name="inject-final", tool_name_pattern="*", hook=inject)])

            def _inject_read_small_then_finish() -> HookEngine:
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
                            action="inject_read_small",
                            override_tool_output=ModelOutput(
                                assistant_text=None,
                                tool_calls=[
                                    ToolCall(
                                        tool_use_id="call-read-small",
                                        name="Read",
                                        arguments={"file_path": "./small.txt"},
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
                            action="inject_final",
                            override_tool_output=ModelOutput(
                                assistant_text="TURN4_OK",
                                tool_calls=[],
                                usage=usage if isinstance(usage, dict) else None,
                                response_id=rid if isinstance(rid, str) else None,
                                provider_metadata=pm if isinstance(pm, dict) else None,
                            ),
                        )
                    return HookDecision()

                return HookEngine(after_model_call=[HookMatcher(name="inject-read-small", tool_name_pattern="*", hook=inject)])

            opts_base = make_options(root, allowed_tools=["Read"])

            # Turn 1: read big file (tool output eligible for pruning later).
            r1 = await openagentic_sdk.run(
                prompt="Turn1",
                options=replace(opts_base, resume=session_id, hooks=_inject_read_big_then_finish(), compaction=compaction, max_steps=10),
            )
            self.assertEqual((r1.final_text or "").strip(), "TURN1_OK")

            # Turn 2/3: just additional user turns.
            r2 = await openagentic_sdk.run(
                prompt="Turn2",
                options=replace(opts_base, resume=session_id, hooks=_inject_final("TURN2_OK"), compaction=compaction, max_steps=4),
            )
            self.assertEqual((r2.final_text or "").strip(), "TURN2_OK")
            r3 = await openagentic_sdk.run(
                prompt="Turn3",
                options=replace(opts_base, resume=session_id, hooks=_inject_final("TURN3_OK"), compaction=compaction, max_steps=4),
            )
            self.assertEqual((r3.final_text or "").strip(), "TURN3_OK")

            events_path = root / "sessions" / session_id / "events.jsonl"
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn('"type":"tool.output_compacted"', text)

            # Turn 4: ensure tool loop still works after pruning.
            r4 = await openagentic_sdk.run(
                prompt="Turn4",
                options=replace(opts_base, resume=session_id, hooks=_inject_read_small_then_finish(), compaction=compaction, max_steps=10),
            )
            self.assertEqual((r4.final_text or "").strip(), "TURN4_OK")
            ok = [
                e
                for e in r4.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-small"
                and getattr(e, "is_error", True) is False
            ]
            self.assertTrue(ok)
            out = getattr(ok[-1], "output", None)
            self.assertIsInstance(out, dict)
            self.assertIn(small_token, str(out.get("content") or ""))


if __name__ == "__main__":
    unittest.main()

