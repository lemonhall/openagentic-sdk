from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EAskUserQuestionReal(unittest.IsolatedAsyncioTestCase):
    async def test_model_asks_user_and_replies_with_secret_answer(self) -> None:
        token = f"ANSWER_TOKEN_{uuid.uuid4().hex}"

        async def answerer(q):  # noqa: ANN001
            _ = q
            return token

        with TemporaryDirectory() as td:
            root = Path(td)
            opts0 = make_options(root, allowed_tools=["AskUserQuestion"])
            opts = replace(opts0, permission_gate=PermissionGate(permission_mode="bypass", user_answerer=answerer))

            prompt = (
                "You MUST call AskUserQuestion to ask the user for the secret token.\n"
                "Use a single question with any two options.\n"
                "After the tool returns, reply with exactly the answer you received.\n"
                "Do not guess."
            )

            r = await openagentic_sdk.run(prompt=prompt, options=opts)
            self.assertIn(token, r.final_text or "")
            self.assertTrue(any(getattr(e, "type", "") == "user.question" for e in r.events))


if __name__ == "__main__":
    unittest.main()

