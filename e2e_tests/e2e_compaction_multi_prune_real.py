from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.options import CompactionOptions
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options, make_provider


class _PrevIdRejectingProvider:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "openai-compatible")
        self.calls: list[tuple[str | None, Sequence[Mapping[str, Any]]]] = []

    async def complete(self, **kwargs: Any) -> ModelOutput:  # pragma: no cover
        return await self._inner.complete(**kwargs)

    async def stream(self, **kwargs: Any):
        prev = kwargs.get("previous_response_id")
        inp = kwargs.get("input") if isinstance(kwargs.get("input"), list) else []
        self.calls.append((prev if isinstance(prev, str) else None, list(inp)))
        if prev is not None:
            raise RuntimeError("previous_response_id unsupported parameter")
        async for ev in self._inner.stream(**kwargs):
            yield ev


class _RecordingProvider:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "openai-compatible")
        self.inputs: list[Sequence[Mapping[str, Any]]] = []

    async def stream(self, **kwargs: Any):
        inp = kwargs.get("input") if isinstance(kwargs.get("input"), list) else []
        self.inputs.append(list(inp))
        async for ev in self._inner.stream(**kwargs):
            yield ev


class TestE2ECompactionMultiPruneReal(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_tool_results_pruned_and_runtime_still_usable(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token_a = f"A_{uuid.uuid4().hex}"
            token_b = f"B_{uuid.uuid4().hex}"
            big_a = ("X" * 8000) + token_a + ("\n" + ("Y" * 8000))
            big_b = ("M" * 8000) + token_b + ("\n" + ("N" * 8000))
            (root / "a.txt").write_text(big_a, encoding="utf-8")
            (root / "b.txt").write_text(big_b, encoding="utf-8")

            stage = 0
            session_id = ""

            async def inject_reads(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read_a",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-a", name="Read", arguments={"file_path": "./a.txt"})],
                            usage=None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_a",
                        override_tool_output=ModelOutput(
                            assistant_text="TURN1_OK",
                            tool_calls=[],
                            usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                if stage == 2:
                    stage = 3
                    return HookDecision(
                        action="inject_read_b",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-b", name="Read", arguments={"file_path": "./b.txt"})],
                            usage=None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                if stage == 3:
                    stage = 4
                    return HookDecision(
                        action="inject_final_b",
                        override_tool_output=ModelOutput(
                            assistant_text="TURN3_OK",
                            tool_calls=[],
                            usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-reads", tool_name_pattern="*", hook=inject_reads)])

            # Make pruning aggressive and ensure runtime goes through the rebuild/prune path.
            compaction = CompactionOptions(auto=False, prune=True, protect_tool_output_tokens=1, min_prune_tokens=1)
            provider0 = _PrevIdRejectingProvider(make_provider())

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts1 = replace(opts0, provider=provider0, compaction=compaction, max_steps=10)

            # Turn 1: read a.txt (big tool result), capture session_id.
            async for ev in openagentic_sdk.query(prompt="Turn1: read a.txt then finish.", options=opts1):
                if getattr(ev, "type", None) == "result":
                    session_id = getattr(ev, "session_id", "") or session_id
            self.assertTrue(session_id)

            # Turn 2: no tool, just another user turn.
            opts2 = replace(opts0, provider=_RecordingProvider(make_provider()), compaction=compaction, resume=session_id, max_steps=2)
            async for _ev in openagentic_sdk.query(prompt="Turn2: reply with TURN2_OK", options=opts2):
                pass

            # Turn 3: read b.txt (second big tool result).
            opts3 = replace(opts0, provider=_RecordingProvider(make_provider()), compaction=compaction, resume=session_id, max_steps=6)
            async for _ev in openagentic_sdk.query(prompt="Turn3: read b.txt then finish.", options=opts3):
                pass

            # Turn 4: another user turn.
            opts4 = replace(opts0, provider=_RecordingProvider(make_provider()), compaction=compaction, resume=session_id, max_steps=2)
            async for _ev in openagentic_sdk.query(prompt="Turn4: reply with TURN4_OK", options=opts4):
                pass

            # Turn 5: triggers pruning for both older tool results and should still be usable.
            provider5 = _RecordingProvider(make_provider())
            opts5 = replace(opts0, provider=provider5, compaction=compaction, resume=session_id, max_steps=2)
            async for _ev in openagentic_sdk.query(prompt="Turn5: reply with TURN5_OK", options=opts5):
                pass

            events_path = root / "sessions" / session_id / "events.jsonl"
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn('"type":"tool.output_compacted"', text)
            self.assertIn('"tool_use_id":"call-read-a"', text)
            self.assertIn('"tool_use_id":"call-read-b"', text)

            joined = "\n".join([str(it) for inp in provider5.inputs for it in inp])
            self.assertIn("Old tool result content cleared", joined)


if __name__ == "__main__":
    unittest.main()

