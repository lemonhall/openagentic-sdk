import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore


class _SlashToolProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        items = list(input)
        self.calls.append(items)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call_1", name="SlashCommand", arguments={"name": "show", "args": ""})],
                response_id="resp_1",
                provider_metadata={"protocol": "responses"},
            )

        out = next(i for i in items if isinstance(i, dict) and i.get("type") == "function_call_output")
        payload = json.loads(out.get("output") or "{}")
        parts = payload.get("parts")
        assert isinstance(parts, list)
        file_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "file"]
        assert file_parts and isinstance(file_parts[0].get("url"), str)
        assert "%23" in file_parts[0]["url"]
        return ModelOutput(assistant_text="ok", tool_calls=(), response_id="resp_2", provider_metadata={"protocol": "responses"})


class TestSlashCommandToolPartsOutput(unittest.IsolatedAsyncioTestCase):
    async def test_slash_command_tool_emits_file_part_with_encoded_uri(self) -> None:
        import openagentic_sdk

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "weird#name.txt").write_text("x", encoding="utf-8")
            (root / ".claude" / "commands").mkdir(parents=True)
            (root / ".claude" / "commands" / "show.md").write_text("@weird#name.txt\n", encoding="utf-8")

            provider = _SlashToolProvider()
            store = FileSessionStore(root_dir=root / "sessions")
            options = OpenAgenticOptions(
                provider=provider,
                model="m",
                api_key="k",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
                allowed_tools=["SlashCommand", "Read", "List"],
            )

            async for _ in openagentic_sdk.query(prompt="x", options=options):
                pass

            self.assertEqual(len(provider.calls), 2)


if __name__ == "__main__":
    unittest.main()

