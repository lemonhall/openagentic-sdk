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


class _PromptNoAnswererWriteProvider:
    name = "offline-permissions-prompt-no-answerer"

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
                response_id="resp-prompt-no-answerer-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "PermissionDenied":
                raise AssertionError(f"expected PermissionDenied, got: {payload.get('error_type')!r}")
            if payload.get("error_message") != "tool use not approved":
                raise AssertionError(f"expected error_message 'tool use not approved', got: {payload.get('error_message')!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_PROMPT_NO_ANSWERER_DENY_OK",
                tool_calls=(),
                response_id="resp-prompt-no-answerer-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflinePermissionsPromptNoAnswererDenies(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_without_user_answerer_denies_and_emits_question(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PROMPT_DENY_{uuid.uuid4().hex}"
            opts0 = make_options_offline(root, provider=_PromptNoAnswererWriteProvider(token=token), allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=None)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="prompt no answerer", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_PROMPT_NO_ANSWERER_DENY_OK")
            self.assertFalse((root / "denied.txt").exists())
            self.assertTrue(any(getattr(e, "type", None) == "user.question" for e in r.events))


if __name__ == "__main__":
    unittest.main()

