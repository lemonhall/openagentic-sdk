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


class _AcceptEditsWriteProvider:
    name = "offline-permissions-accept-edits"

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
                        arguments={"file_path": "accept.txt", "content": self.token, "overwrite": True},
                    )
                ],
                response_id="resp-accept-edits-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected write success, got: {payload!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_ACCEPT_EDITS_OK",
                tool_calls=(),
                response_id="resp-accept-edits-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflinePermissionsAcceptEditsAllowsWriteNoPrompt(unittest.IsolatedAsyncioTestCase):
    async def test_accept_edits_allows_write_without_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ACCEPT_{uuid.uuid4().hex}"

            provider = _AcceptEditsWriteProvider(token=token)
            opts0 = make_options_offline(root, provider=provider, allowed_tools=["Write"])

            async def _should_not_be_called(_q):  # noqa: ANN001
                raise AssertionError("user_answerer should not be called in acceptEdits for Write")

            gate = PermissionGate(permission_mode="acceptEdits", interactive=False, user_answerer=_should_not_be_called)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="acceptEdits write", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_ACCEPT_EDITS_OK")

            self.assertFalse(any(getattr(e, "type", None) == "user.question" for e in r.events))
            p = root / "accept.txt"
            self.assertTrue(p.exists())
            self.assertIn(token, p.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()

