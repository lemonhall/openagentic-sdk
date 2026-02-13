from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from openagentic_sdk.permissions.gate import PermissionGate


class _ReadToolProvider:
    name = "offline-permission-prompt"

    def __init__(self) -> None:
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, input, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        self._n += 1
        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "a.txt"})],
                response_id="resp-perm-1",
                provider_metadata={"protocol": "responses"},
            )
        return ModelOutput(
            assistant_text="E2E_OFFLINE_PERMISSION_OK",
            tool_calls=(),
            response_id="resp-perm-2",
            provider_metadata={"protocol": "responses"},
        )


class TestE2EOfflinePermissionPromptUserAnswerer(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_emits_question_and_allows_when_user_answers_yes(self) -> None:
        async def _answer(q):  # noqa: ANN001
            _ = q
            return "yes"

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("hello", encoding="utf-8")

            opts = make_options_offline(root, provider=_ReadToolProvider(), allowed_tools=["Read"])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=_answer)
            opts = replace(opts, permission_gate=gate)

            r = await openagentic_sdk.run(prompt="read with prompt permissions", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_PERMISSION_OK")
            types = [getattr(e, "type", None) for e in r.events]
            self.assertIn("user.question", types)


if __name__ == "__main__":
    unittest.main()

