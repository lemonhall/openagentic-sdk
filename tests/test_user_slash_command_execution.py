import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk import query
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.sessions.store import FileSessionStore


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    async def complete(self, *, model: str, messages, tools=(), api_key=None):
        _ = (model, tools, api_key)
        self.seen.append(list(messages))
        return ModelOutput(assistant_text="ok", tool_calls=(), usage={"total_tokens": 1})


class TestUserSlashCommandExecution(unittest.IsolatedAsyncioTestCase):
    async def test_user_prompt_slash_command_expands_before_model_call(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "input.txt").write_text("filedata", encoding="utf-8")

            (root / ".opencode" / "commands").mkdir(parents=True)
            (root / ".opencode" / "commands" / "hello.md").write_text(
                "Hello $1\nINCLUDED: @input.txt\n",
                encoding="utf-8",
            )

            store = FileSessionStore(root_dir=root)
            provider = RecordingProvider()
            options = OpenAgenticOptions(
                provider=provider,
                model="m",
                api_key="k",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
            )

            async for _ in query(prompt="/hello world", options=options):
                pass

            self.assertTrue(provider.seen)
            # Last message in first call should be the expanded user command.
            first_call = provider.seen[0]
            user_msgs = [m for m in first_call if isinstance(m, dict) and m.get("role") == "user"]
            self.assertTrue(user_msgs)
            content = user_msgs[-1].get("content")
            self.assertIsInstance(content, str)
            self.assertIn("Hello world", content)
            self.assertIn("filedata", content)
            self.assertNotIn("Called the Read tool", content)
            self.assertNotIn("Called the list tool", content)


if __name__ == "__main__":
    unittest.main()
