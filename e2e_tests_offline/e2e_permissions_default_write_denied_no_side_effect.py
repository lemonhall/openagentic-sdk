from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _DefaultWriteDeniedProvider:
    name = "offline-permissions-default-write-denied"

    def __init__(self, *, token: str) -> None:
        self._n = 0
        self.token = token

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
                        arguments={"file_path": "denied.txt", "content": self.token, "overwrite": True},
                    )
                ],
                response_id="resp-default-deny-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "PermissionDenied":
                raise AssertionError(f"expected PermissionDenied, got: {payload.get('error_type')!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_DEFAULT_DENY_OK",
                tool_calls=(),
                response_id="resp-default-deny-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflinePermissionsDefaultWriteDeniedNoSideEffect(unittest.IsolatedAsyncioTestCase):
    async def test_default_mode_denies_write_when_user_answers_no(self) -> None:
        async def _answer_no(_q: Any) -> str:
            return "no"

        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"DENY_{uuid.uuid4().hex}"
            p = root / "denied.txt"

            provider = _DefaultWriteDeniedProvider(token=token)
            opts0 = make_options_offline(root, provider=provider, allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=_answer_no)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="default write denied", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_DEFAULT_DENY_OK")
            self.assertFalse(p.exists(), "denied write should not create denied.txt")
            self.assertTrue(any(getattr(e, "type", None) == "user.question" for e in r.events))


if __name__ == "__main__":
    unittest.main()

