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
        self.prev_ids: list[str | None] = []

    async def complete(
        self,
        *,
        model: str,
        input: Sequence[Mapping[str, Any]],
        instructions: str | None = None,
        tools: Sequence[Mapping[str, Any]] = (),
        api_key: str | None = None,
        previous_response_id: str | None = None,
        store: bool = True,
        include: Sequence[str] = (),
    ) -> ModelOutput:
        self.prev_ids.append(previous_response_id)
        if previous_response_id is not None:
            raise RuntimeError("previous_response_id unsupported parameter")
        return await self._inner.complete(
            model=model,
            input=input,
            instructions=instructions,
            tools=tools,
            api_key=api_key,
            previous_response_id=previous_response_id,
            store=store,
            include=include,
        )


class TestE2ECompactionAutoSummaryPivotReal(unittest.IsolatedAsyncioTestCase):
    async def test_auto_compaction_emits_marker_and_summary_pivot(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"FIXTURE_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            stage = 0

            async def inject_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                # First model call: inject a tool use so the runtime makes a second model call
                # that tries to thread via previous_response_id.
                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                # Second model call (after tool results): end, but spoof usage totals large enough to
                # trigger auto-compaction once supports_previous_response_id flips to False.
                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="COMPACTION_OK",
                            tool_calls=[],
                            usage={"total_tokens": 100_000, "input_tokens": 100_000, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                # Third model call (after compaction injects "Continue..."): finish without further overflow.
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

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read-then-finish", tool_name_pattern="*", hook=inject_read_then_finish)])

            inner = make_provider()
            provider = _PrevIdRejectingProvider(inner)

            # Trigger overflow exactly once: large totals overflow the usable window, then small totals do not.
            compaction = CompactionOptions(auto=True, prune=True, context_limit=5_000)

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, provider=provider, compaction=compaction, max_steps=20)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./a.txt, then finish.", options=opts):
                events.append(ev)

            # Verify we attempted previous_response_id threading at least once.
            self.assertTrue(any(isinstance(x, str) and x for x in provider.prev_ids))

            saw_compaction = any(
                getattr(e, "type", None) == "user.compaction"
                and getattr(e, "auto", False) is True
                and getattr(e, "reason", None) == "overflow"
                for e in events
            )
            self.assertTrue(saw_compaction)

            saw_summary = any(
                getattr(e, "type", None) == "assistant.message" and getattr(e, "is_summary", False) is True for e in events
            )
            self.assertTrue(saw_summary)

            results = [e for e in events if getattr(e, "type", None) == "result"]
            self.assertTrue(results)
            pm = getattr(results[-1], "provider_metadata", None)
            self.assertIsInstance(pm, dict)
            self.assertIs(pm.get("supports_previous_response_id"), False)


if __name__ == "__main__":
    unittest.main()
