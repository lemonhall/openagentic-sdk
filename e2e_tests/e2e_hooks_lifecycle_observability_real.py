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

from e2e_tests._harness import make_options, make_provider


class _PrevIdRejectingProvider:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "openai-compatible")

    async def complete(self, **kwargs: Any) -> Any:
        return await self._inner.complete(**kwargs)

    async def stream(self, **kwargs: Any):
        prev = kwargs.get("previous_response_id")
        if prev is not None:
            raise RuntimeError("previous_response_id unsupported parameter")
        async for ev in self._inner.stream(**kwargs):
            yield ev


class TestE2EHooksLifecycleObservabilityReal(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_hook_points_emit_hook_events(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"FIXTURE_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            stage = 0

            async def inject_read_and_overflow(payload: Mapping[str, Any]) -> HookDecision:
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
                        action="inject_overflow",
                        override_tool_output=ModelOutput(
                            assistant_text="OVERFLOW_OK",
                            tool_calls=[],
                            usage={"total_tokens": 100_000, "input_tokens": 100_000, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                if stage == 2:
                    stage = 3
                    return HookDecision(
                        action="inject_done",
                        override_tool_output=ModelOutput(
                            assistant_text="DONE_OK",
                            tool_calls=[],
                            usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                return HookDecision()

            async def mark(_: Mapping[str, Any]) -> HookDecision:
                return HookDecision(action="marked")

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject", tool_name_pattern="*", hook=inject_read_and_overflow)],
                session_start=[HookMatcher(name="start", tool_name_pattern="*", hook=mark)],
                session_end=[HookMatcher(name="end", tool_name_pattern="*", hook=mark)],
                stop=[HookMatcher(name="stop", tool_name_pattern="*", hook=mark)],
                session_compacting=[HookMatcher(name="compacting", tool_name_pattern="*", hook=mark)],
            )

            compaction = CompactionOptions(auto=True, prune=True, context_limit=5_000)
            provider = _PrevIdRejectingProvider(make_provider())
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, provider=provider, compaction=compaction, max_steps=20)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./a.txt then finish.", options=opts):
                events.append(ev)

            hook_events = [e for e in events if getattr(e, "type", None) == "hook.event"]
            self.assertTrue(hook_events)
            points = {getattr(e, "hook_point", "") for e in hook_events}
            self.assertIn("SessionStart", points)
            self.assertIn("Stop", points)
            self.assertIn("SessionEnd", points)
            self.assertIn("SessionCompacting", points)


if __name__ == "__main__":
    unittest.main()
