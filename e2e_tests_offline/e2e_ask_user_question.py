from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from openagentic_sdk.permissions.gate import PermissionGate


class _AskUserQuestionProvider:
    name = "offline-ask-user-question"

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
                        tool_use_id="call-aq-1",
                        name="AskUserQuestion",
                        arguments={
                            "questions": [{"question": "pick", "options": [{"label": "A"}, {"label": "B"}]}],
                        },
                    )
                ],
                response_id="resp-aq-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            out = next((x for x in items if isinstance(x, dict) and x.get("type") == "function_call_output"), None)
            if not isinstance(out, dict) or out.get("call_id") != "call-aq-1":
                raise AssertionError("expected AskUserQuestion function_call_output for call-aq-1")
            payload_raw = out.get("output")
            if not isinstance(payload_raw, str) or not payload_raw:
                raise AssertionError("expected JSON string tool output")
            payload = json.loads(payload_raw)
            answers = payload.get("answers")
            if not isinstance(answers, dict) or answers.get("pick") != "A":
                raise AssertionError(f"unexpected answers: {answers!r}")

            return ModelOutput(
                assistant_text="E2E_OFFLINE_ASK_USER_OK",
                tool_calls=(),
                response_id="resp-aq-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineAskUserQuestion(unittest.IsolatedAsyncioTestCase):
    async def test_ask_user_question_emits_user_question_and_returns_answer(self) -> None:
        async def _answerer(q):  # noqa: ANN001
            self.assertEqual(q.prompt, "pick")
            self.assertEqual(q.choices, ["A", "B"])
            return "A"

        with TemporaryDirectory() as td:
            root = Path(td)
            provider = _AskUserQuestionProvider()
            opts = make_options_offline(root, provider=provider, allowed_tools=["AskUserQuestion"])
            gate = PermissionGate(permission_mode="bypass", user_answerer=_answerer)
            opts = replace(opts, permission_gate=gate)

            r = await openagentic_sdk.run(prompt="ask me", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_ASK_USER_OK")
            self.assertTrue(any(getattr(e, "type", "") == "user.question" for e in r.events))


if __name__ == "__main__":
    unittest.main()

