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
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options, make_provider


class _PrevIdRejectingProvider:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "openai-compatible")
        self.prev_ids: list[str | None] = []
        self.inputs: list[Sequence[Mapping[str, Any]]] = []

    async def stream(self, **kwargs: Any):
        prev = kwargs.get("previous_response_id")
        inp = kwargs.get("input") if isinstance(kwargs.get("input"), list) else []
        self.prev_ids.append(prev if isinstance(prev, str) else None)
        self.inputs.append(list(inp))
        if prev is not None:
            raise RuntimeError("previous_response_id unsupported parameter")
        async for ev in self._inner.stream(**kwargs):
            yield ev


class TestE2EResumeAfterFallbackNoThreadingReal(unittest.IsolatedAsyncioTestCase):
    async def test_resumed_session_does_not_thread_previous_response_id(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"FIXTURE_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

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
                            assistant_text="FALLBACK_OK",
                            tool_calls=[],
                            usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )
                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read_then_finish)])
            provider = _PrevIdRejectingProvider(make_provider())
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts1 = replace(opts0, provider=provider, max_steps=10)

            events1: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./a.txt and finish.", options=opts1):
                events1.append(ev)
                if getattr(ev, "type", None) == "result":
                    session_id = getattr(ev, "session_id", "") or session_id

            self.assertTrue(session_id)

            provider2 = _PrevIdRejectingProvider(make_provider())
            opts2 = replace(opts0, provider=provider2, resume=session_id, max_steps=3)
            async for _ev in openagentic_sdk.query(prompt="Reply with exactly: RESUME_OK", options=opts2):
                pass

            self.assertTrue(provider2.prev_ids)
            self.assertTrue(all(p is None for p in provider2.prev_ids))

            # Resumed input should use Responses items, not chat role=tool.
            joined = "\n".join([str(it) for inp in provider2.inputs for it in inp])
            self.assertIn("'type': 'function_call_output'", joined)
            self.assertNotIn("'role': 'tool'", joined)


if __name__ == "__main__":
    unittest.main()

