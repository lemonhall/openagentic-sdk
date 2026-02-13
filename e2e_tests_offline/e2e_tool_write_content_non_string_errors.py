from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _WriteNonStringContentProvider:
    name = "offline-tool-write-non-string"

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
                        arguments={"file_path": "a.txt", "content": {"not": "a string"}, "overwrite": True},
                    )
                ],
                response_id="resp-non-string-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "ValueError":
                raise AssertionError(f"expected ValueError, got: {payload.get('error_type')!r}")
            msg = str(payload.get("error_message") or "")
            if "content" not in msg:
                raise AssertionError(f"expected content type error, got: {msg!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_WRITE_NON_STRING_OK",
                tool_calls=(),
                response_id="resp-non-string-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineToolWriteContentNonStringErrors(unittest.IsolatedAsyncioTestCase):
    async def test_write_non_string_content_errors_and_is_serialized(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            opts0 = make_options_offline(root, provider=_WriteNonStringContentProvider(), allowed_tools=["Write"])
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="write non-string", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_WRITE_NON_STRING_OK")
            self.assertFalse((root / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()

