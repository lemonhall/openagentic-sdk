from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _WriteWithCallbackProvider:
    name = "offline-permissions-callback-raises"

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
                        arguments={"file_path": "x.txt", "content": "X", "overwrite": True},
                    )
                ],
                response_id="resp-callback-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "PermissionDenied":
                raise AssertionError(f"expected PermissionDenied, got: {payload.get('error_type')!r}")
            msg = str(payload.get("error_message") or "")
            if "permission callback error:" not in msg:
                raise AssertionError(f"expected callback error message, got: {msg!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_CALLBACK_RAISE_DENY_OK",
                tool_calls=(),
                response_id="resp-callback-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflinePermissionsCallbackApproverRaisesDenies(unittest.IsolatedAsyncioTestCase):
    async def test_callback_exception_denies_with_diagnostic_message(self) -> None:
        async def _approver(_tool_name: str, _tool_input: Mapping[str, Any], _context: Mapping[str, Any]) -> bool:
            raise RuntimeError("boom")

        with TemporaryDirectory() as td:
            root = Path(td)
            opts0 = make_options_offline(root, provider=_WriteWithCallbackProvider(), allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="callback", approver=_approver)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="callback raises", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_CALLBACK_RAISE_DENY_OK")
            self.assertFalse((root / "x.txt").exists())
            self.assertFalse(any(getattr(e, "type", None) == "user.question" for e in r.events))


if __name__ == "__main__":
    unittest.main()

