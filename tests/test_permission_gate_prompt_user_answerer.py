import unittest

from openagentic_sdk.permissions.gate import PermissionGate


class TestPermissionGatePromptUserAnswerer(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_returns_question_and_allows_on_yes(self) -> None:
        async def answerer(q):  # noqa: ANN001
            self.assertTrue(q.question_id)
            self.assertIn("Allow tool Read?", q.prompt)
            self.assertEqual(q.choices, ["yes", "no"])
            return "yes"

        gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answerer)
        res = await gate.approve("Read", {"file_path": "a.txt"}, context={"tool_use_id": "t1", "agent_name": "a1"})
        self.assertTrue(res.allowed)
        self.assertIsNotNone(res.question)
        self.assertEqual(res.question.question_id, "t1")


if __name__ == "__main__":
    unittest.main()

