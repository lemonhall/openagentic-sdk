from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _ReadOffsetLimitProvider:
    name = "offline-tool-read-offset-limit"

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
                        tool_use_id="call-read-1",
                        name="Read",
                        arguments={"file_path": "a.txt", "offset": 2, "limit": 1},
                    )
                ],
                response_id="resp-read-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-read-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected read success, got: {payload!r}")
            content = str(payload.get("content") or "")
            if not content.startswith("2: "):
                raise AssertionError(f"expected numbered content starting with '2: ', got: {content!r}")
            if payload.get("total_lines") != 3:
                raise AssertionError(f"expected total_lines=3, got: {payload.get('total_lines')!r}")
            if payload.get("lines_returned") != 1:
                raise AssertionError(f"expected lines_returned=1, got: {payload.get('lines_returned')!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_READ_OFFSET_LIMIT_OK",
                tool_calls=(),
                response_id="resp-read-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineToolReadOffsetLimitNumbered(unittest.IsolatedAsyncioTestCase):
    async def test_read_offset_limit_returns_numbered_lines(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")

            opts0 = make_options_offline(root, provider=_ReadOffsetLimitProvider(), allowed_tools=["Read"])
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="read offset limit", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_READ_OFFSET_LIMIT_OK")


if __name__ == "__main__":
    unittest.main()

