from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _AbsPathOutsideReadThenInsideProvider:
    name = "offline-security-abs-outside"

    def __init__(self, *, outside_abs: str, outside_token: str, inside_token: str) -> None:
        self._n = 0
        self.outside_abs = outside_abs
        self.outside_token = outside_token
        self.inside_token = inside_token

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        items = list(input)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call-read-outside-1", name="Read", arguments={"file_path": self.outside_abs})],
                response_id="resp-abs-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-read-outside-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "ValueError":
                raise AssertionError(f"expected ValueError, got: {payload.get('error_type')!r}")
            em = str(payload.get("error_message") or "")
            if self.outside_token in em:
                raise AssertionError("outside file content must not leak into error_message")
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call-read-inside-1", name="Read", arguments={"file_path": "./inside.txt"})],
                response_id="resp-abs-2",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 3:
            payload = get_function_call_output_payload(items, call_id="call-read-inside-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected inside read success, got: {payload!r}")
            if self.inside_token not in str(payload.get("content") or ""):
                raise AssertionError(f"expected inside token in content, got: {payload!r}")
            return ModelOutput(
                assistant_text=self.inside_token,
                tool_calls=(),
                response_id="resp-abs-3",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineSecurityAbsPathOutsideRejected(unittest.IsolatedAsyncioTestCase):
    async def test_abs_path_outside_project_is_rejected_and_not_leaked(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / "outside.txt"
            outside_token = f"OUTSIDE_{uuid.uuid4().hex}"
            inside_token = f"INSIDE_{uuid.uuid4().hex}"
            outside.write_text(outside_token, encoding="utf-8")
            (root / "inside.txt").write_text(inside_token, encoding="utf-8")

            try:
                provider = _AbsPathOutsideReadThenInsideProvider(
                    outside_abs=str(outside),
                    outside_token=outside_token,
                    inside_token=inside_token,
                )
                opts0 = make_options_offline(root, provider=provider, allowed_tools=["Read"])
                opts = replace(opts0, max_steps=10)

                r = await openagentic_sdk.run(prompt="abs path security", options=opts)
                self.assertEqual(r.final_text.strip(), inside_token)
                self.assertNotIn(outside_token, r.final_text)
            finally:
                if outside.exists():
                    outside.unlink()


if __name__ == "__main__":
    unittest.main()

