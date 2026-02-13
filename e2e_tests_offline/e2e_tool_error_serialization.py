from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _ToolErrorSerializationProvider:
    name = "offline-tool-error-serialization"

    def __init__(self) -> None:
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        items = list(input)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call-read-missing-1", name="Read", arguments={"file_path": "missing.txt"})],
                response_id="resp-err-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            out = next((x for x in items if isinstance(x, dict) and x.get("type") == "function_call_output"), None)
            if not isinstance(out, dict) or out.get("call_id") != "call-read-missing-1":
                raise AssertionError("expected function_call_output for missing read")
            payload_raw = out.get("output")
            if not isinstance(payload_raw, str) or not payload_raw:
                raise AssertionError("expected JSON string tool output")
            payload = json.loads(payload_raw)
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "FileNotFoundError":
                raise AssertionError(f"expected FileNotFoundError, got: {payload.get('error_type')!r}")
            em = str(payload.get("error_message") or "")
            if "missing.txt" not in em:
                raise AssertionError(f"expected missing filename in error_message, got: {em!r}")

            return ModelOutput(
                assistant_text="E2E_OFFLINE_TOOL_ERROR_OK",
                tool_calls=(),
                response_id="resp-err-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineToolErrorSerialization(unittest.IsolatedAsyncioTestCase):
    async def test_tool_errors_are_serialized_into_function_call_output(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            provider = _ToolErrorSerializationProvider()
            opts = make_options_offline(root, provider=provider, allowed_tools=["Read"])
            r = await openagentic_sdk.run(prompt="read missing", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_TOOL_ERROR_OK")
            self.assertTrue(any(getattr(e, "type", "") == "tool.result" and bool(getattr(e, "is_error", False)) for e in r.events))


if __name__ == "__main__":
    unittest.main()

