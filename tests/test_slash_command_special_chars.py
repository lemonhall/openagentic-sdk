import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk import query
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore


class LegacyProviderAsksSlashCommandOnce:
    name = "legacy-slash"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def complete(self, *, model: str, messages, tools=(), api_key=None):
        _ = (model, tools, api_key)
        msgs = list(messages)
        self.calls.append(msgs)

        if len(self.calls) == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="sc_1", name="SlashCommand", arguments={"name": "readhash", "args": ""})],
                usage={"total_tokens": 1},
            )

        tool_msgs = [m for m in msgs if isinstance(m, dict) and m.get("role") == "tool"]
        if not tool_msgs:
            raise AssertionError("expected tool message")
        payload = json.loads(tool_msgs[-1].get("content") or "{}")
        parts = payload.get("parts")
        if not isinstance(parts, list):
            raise AssertionError("expected parts list")

        file_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "file"]
        if len(file_parts) != 1:
            raise AssertionError("expected 1 file part")
        fp = file_parts[0]
        if fp.get("filename") != "file#name.txt":
            raise AssertionError("expected filename to preserve ref")
        url = fp.get("url")
        if not isinstance(url, str) or "%23" not in url:
            raise AssertionError("expected URL encoding for # character")

        content = payload.get("content")
        if not isinstance(content, str) or "special content" not in content:
            raise AssertionError("expected referenced file content injected into content")
        if "Called the Read tool" in content:
            raise AssertionError("expected no tool transcript prefix")

        return ModelOutput(assistant_text="ok", tool_calls=(), usage={"total_tokens": 2})


class TestSlashCommandSpecialChars(unittest.IsolatedAsyncioTestCase):
    async def test_hash_in_filename_is_url_encoded_and_content_injected(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()

            (root / "file#name.txt").write_text("special content\n", encoding="utf-8")

            (root / ".opencode" / "commands").mkdir(parents=True)
            (root / ".opencode" / "commands" / "readhash.md").write_text(
                "Read @file#name.txt\n",
                encoding="utf-8",
            )

            store = FileSessionStore(root_dir=root)
            provider = LegacyProviderAsksSlashCommandOnce()
            options = OpenAgenticOptions(
                provider=provider,
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
            )

            async for _ in query(prompt="run cmd", options=options):
                pass


if __name__ == "__main__":
    unittest.main()

