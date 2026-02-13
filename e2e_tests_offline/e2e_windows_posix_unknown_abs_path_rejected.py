from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _ReadUnknownPosixAbsProvider:
    name = "offline-windows-posix-unknown-abs"

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
                tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "/etc/passwd"})],
                response_id="resp-unknown-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-read-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "ValueError":
                raise AssertionError(f"expected ValueError, got: {payload.get('error_type')!r}")
            msg = str(payload.get("error_message") or "")
            if "Tool path must be under project root" not in msg:
                raise AssertionError(f"expected project-root block message, got: {msg!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_UNKNOWN_POSIX_ABS_REJECT_OK",
                tool_calls=(),
                response_id="resp-unknown-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineWindowsPosixUnknownAbsPathRejected(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_posix_absolute_path_is_rejected(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            opts0 = make_options_offline(root, provider=_ReadUnknownPosixAbsProvider(), allowed_tools=["Read"])
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="read unknown abs", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_UNKNOWN_POSIX_ABS_REJECT_OK")


if __name__ == "__main__":
    unittest.main()

