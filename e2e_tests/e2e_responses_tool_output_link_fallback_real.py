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


class _LinkRejectingProvider:
    """Provider wrapper that simulates a gateway rejecting outputs-only continuations.

    This triggers the runtime_core retry path that prepends `function_call` items
    for the pending tool calls.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "openai-compatible")
        self.calls: list[tuple[str | None, Sequence[Mapping[str, Any]]]] = []

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
        self.calls.append((previous_response_id, list(input)))

        # Simulate the OpenAI-style error text that runtime_core detects.
        if previous_response_id is not None:
            items = list(input)
            if items and all(isinstance(it, dict) and it.get("type") == "function_call_output" for it in items):
                call_id = items[0].get("call_id") if isinstance(items[0], dict) else None
                raise RuntimeError(f"No tool call found for function call output: call_id={call_id}")

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


class TestE2EResponsesToolOutputLinkFallbackReal(unittest.IsolatedAsyncioTestCase):
    async def test_outputs_only_rejection_triggers_retry_with_function_calls(self) -> None:
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

                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="LINK_FALLBACK_OK",
                            tool_calls=[],
                            usage={"total_tokens": 1, "input_tokens": 1, "output_tokens": 0},
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read-then-finish", tool_name_pattern="*", hook=inject_read_then_finish)])

            inner = make_provider()
            provider = _LinkRejectingProvider(inner)

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, provider=provider, max_steps=10)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./a.txt and finish.", options=opts):
                events.append(ev)

            # Ensure we hit the error injection path at least once.
            saw_outputs_only_with_prev = any(
                prev is not None
                and inp
                and all(isinstance(it, dict) and it.get("type") == "function_call_output" for it in inp)
                for prev, inp in provider.calls
            )
            self.assertTrue(saw_outputs_only_with_prev)

            # Ensure the retry input includes `function_call` items (prepended) for the same call id.
            saw_prepended_calls = False
            for prev, inp in provider.calls:
                if prev is not None:
                    continue
                if not inp or not all(isinstance(it, dict) for it in inp):
                    continue
                call_ids_calls = {it.get("call_id") for it in inp if it.get("type") == "function_call" and isinstance(it.get("call_id"), str)}
                call_ids_outs = {
                    it.get("call_id") for it in inp if it.get("type") == "function_call_output" and isinstance(it.get("call_id"), str)
                }
                if "call-read-1" in call_ids_calls and "call-read-1" in call_ids_outs:
                    saw_prepended_calls = True
                    break
            self.assertTrue(saw_prepended_calls)

            results = [e for e in events if getattr(e, "type", None) == "result"]
            self.assertTrue(results)
            pm = getattr(results[-1], "provider_metadata", None)
            self.assertIsInstance(pm, dict)
            self.assertIs(pm.get("supports_previous_response_id"), False)


if __name__ == "__main__":
    unittest.main()

