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


class TestE2ECompactionPruneToolOutputsReal(unittest.IsolatedAsyncioTestCase):
    async def test_prune_marks_old_tool_results_and_rebuild_uses_placeholder(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PRUNE_TOKEN_{uuid.uuid4().hex}"
            big = ("X" * 8000) + token + ("\n" + ("Y" * 8000))
            (root / "a.txt").write_text(big, encoding="utf-8")

            stage = 0
            session_id = ""

            async def inject_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None
                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
                            usage=None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final",
                        override_tool_output=ModelOutput(
                            assistant_text="DONE_OK",
                            tool_calls=[],
                            # Force compaction eligibility if needed later; pruning does not depend on this.
                            usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read_then_finish)])
            inner = make_provider()
            provider1 = _PrevIdRejectingProvider(inner)

            # Make pruning aggressive.
            compaction = CompactionOptions(auto=False, prune=True, protect_tool_output_tokens=1, min_prune_tokens=1)

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts1 = replace(opts0, provider=provider1, compaction=compaction, max_steps=10)

            events1: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./a.txt and finish.", options=opts1):
                events1.append(ev)
                if getattr(ev, "type", None) == "result":
                    session_id = getattr(ev, "session_id", "") or session_id

            self.assertTrue(session_id)

            # Second run adds a second user turn but does not prune yet (OpenCode parity: skip until >=2 turns).
            opts2 = replace(opts0, provider=_RecordingProvider(make_provider()), compaction=compaction, resume=session_id, max_steps=2)
            async for _ev in openagentic_sdk.query(prompt="Reply with exactly: TURN2_OK", options=opts2):
                pass

            # Third run: now the first tool result is older than 2 user turns and is eligible for pruning.
            provider3 = _RecordingProvider(make_provider())
            opts3 = replace(opts0, provider=provider3, compaction=compaction, resume=session_id, max_steps=2)
            async for _ev in openagentic_sdk.query(prompt="Reply with exactly: PRUNE_OK", options=opts3):
                pass

            # Assert tool.output_compacted exists on disk.
            events_path = root / "sessions" / session_id / "events.jsonl"
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn('"type":"tool.output_compacted"', text)

            # Assert rebuilt provider input uses the placeholder for compacted outputs.
            joined = "\n".join([str(it) for inp in provider3.inputs for it in inp])
            self.assertIn("Old tool result content cleared", joined)


if __name__ == "__main__":
    unittest.main()
