from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _WriteOverwriteFalseProvider:
    name = "offline-tool-write-overwrite-false"

    def __init__(self, *, token1: str) -> None:
        self._n = 0
        self.token1 = token1

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
                        arguments={"file_path": "a.txt", "content": self.token1, "overwrite": True},
                    )
                ],
                response_id="resp-ow-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected initial write success, got: {payload!r}")
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call-write-2",
                        name="Write",
                        arguments={"file_path": "a.txt", "content": "SHOULD_FAIL", "overwrite": False},
                    )
                ],
                response_id="resp-ow-2",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 3:
            payload = get_function_call_output_payload(items, call_id="call-write-2")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "FileExistsError":
                raise AssertionError(f"expected FileExistsError, got: {payload.get('error_type')!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_OVERWRITE_FALSE_OK",
                tool_calls=(),
                response_id="resp-ow-3",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineToolWriteOverwriteFalseRaises(unittest.IsolatedAsyncioTestCase):
    async def test_overwrite_false_raises_file_exists_and_does_not_change_content(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token1 = f"OW_{uuid.uuid4().hex}"
            opts0 = make_options_offline(
                root,
                provider=_WriteOverwriteFalseProvider(token1=token1),
                allowed_tools=["Write"],
            )
            opts = replace(opts0, max_steps=10)

            r = await openagentic_sdk.run(prompt="overwrite false", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_OVERWRITE_FALSE_OK")
            p = root / "a.txt"
            self.assertTrue(p.exists())
            self.assertIn(token1, p.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()

