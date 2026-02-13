from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _WriteNotAllowedProvider:
    name = "offline-allowed-tools-tool-not-allowed"

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
                tool_calls=[
                    ToolCall(
                        tool_use_id="call-write-1",
                        name="Write",
                        arguments={"file_path": "a.txt", "content": "SHOULD_NOT_WRITE", "overwrite": True},
                    )
                ],
                response_id="resp-not-allowed-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "ToolNotAllowed":
                raise AssertionError(f"expected ToolNotAllowed, got: {payload.get('error_type')!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_TOOL_NOT_ALLOWED_OK",
                tool_calls=(),
                response_id="resp-not-allowed-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineAllowedToolsToolNotAllowed(unittest.IsolatedAsyncioTestCase):
    async def test_not_allowed_tool_is_denied_and_serialized(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "a.txt"

            opts0 = make_options_offline(root, provider=_WriteNotAllowedProvider(), allowed_tools=[])
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="try a denied tool", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_TOOL_NOT_ALLOWED_OK")
            self.assertFalse(p.exists(), "Write should not have created a.txt")

            denied = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "is_error", False) is True
                and getattr(e, "error_type", "") == "ToolNotAllowed"
            ]
            self.assertTrue(denied, "expected a ToolNotAllowed tool.result event")


if __name__ == "__main__":
    unittest.main()

