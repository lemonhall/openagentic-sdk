from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _TodoWriteToolLoopProvider:
    name = "offline-todowrite-tool-loop"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        items = list(input)
        self.calls.append(items)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call-1",
                        name="TodoWrite",
                        arguments={"todos": [{"content": "e2e item", "status": "completed"}]},
                    )
                ],
                response_id="resp-tool-loop-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            out = next((x for x in items if isinstance(x, dict) and x.get("type") == "function_call_output"), None)
            if not isinstance(out, dict):
                raise AssertionError("expected a function_call_output item in second call input")
            if out.get("call_id") != "call-1":
                raise AssertionError(f"expected call_id=call-1, got {out.get('call_id')!r}")
            output_payload = out.get("output")
            if isinstance(output_payload, str):
                try:
                    output_payload = json.loads(output_payload)
                except json.JSONDecodeError as e:
                    raise AssertionError(f"expected JSON tool output, got: {output_payload!r}") from e
            if not isinstance(output_payload, dict) or output_payload.get("message") != "Updated todos":
                raise AssertionError(f"unexpected tool output payload: {output_payload!r}")

            return ModelOutput(
                assistant_text="E2E_OFFLINE_TOOL_LOOP_OK",
                tool_calls=(),
                response_id="resp-tool-loop-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineToolLoopTodoWrite(unittest.IsolatedAsyncioTestCase):
    async def test_run_executes_tool_and_continues(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            provider = _TodoWriteToolLoopProvider()
            opts = make_options_offline(root, provider=provider, allowed_tools=["TodoWrite"])
            r = await openagentic_sdk.run(prompt="write a todo via tool", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_TOOL_LOOP_OK")
            self.assertEqual(len(provider.calls), 2)


if __name__ == "__main__":
    unittest.main()
