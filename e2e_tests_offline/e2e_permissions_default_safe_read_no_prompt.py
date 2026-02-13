from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _DefaultSafeReadProvider:
    name = "offline-permissions-default-safe-read"

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
                tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "a.txt"})],
                response_id="resp-default-safe-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-read-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected read success, got: {payload!r}")
            if self.token not in str(payload.get("content") or ""):
                raise AssertionError(f"expected token in read content, got: {payload!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_DEFAULT_SAFE_OK",
                tool_calls=(),
                response_id="resp-default-safe-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflinePermissionsDefaultSafeReadNoPrompt(unittest.IsolatedAsyncioTestCase):
    async def test_default_mode_allows_read_without_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"DEFAULT_SAFE_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            provider = _DefaultSafeReadProvider(token=token)
            opts0 = make_options_offline(root, provider=provider, allowed_tools=["Read"])

            async def _should_not_be_called(_q):  # noqa: ANN001
                raise AssertionError("user_answerer should not be called for safe Read in default mode")

            gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=_should_not_be_called)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="default safe read", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_DEFAULT_SAFE_OK")
            self.assertFalse(any(getattr(e, "type", None) == "user.question" for e in r.events))


if __name__ == "__main__":
    unittest.main()

