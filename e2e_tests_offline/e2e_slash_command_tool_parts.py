from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _SlashCommandToolProvider:
    name = "offline-slash-command-tool"

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
                tool_calls=[ToolCall(tool_use_id="call-sc-1", name="SlashCommand", arguments={"name": "show", "args": ""})],
                response_id="resp-sc-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            out = next((x for x in items if isinstance(x, dict) and x.get("type") == "function_call_output"), None)
            if not isinstance(out, dict) or out.get("call_id") != "call-sc-1":
                raise AssertionError("expected SlashCommand function_call_output for call-sc-1")
            payload_raw = out.get("output")
            if not isinstance(payload_raw, str) or not payload_raw:
                raise AssertionError("expected JSON string tool output")
            payload = json.loads(payload_raw)
            parts = payload.get("parts")
            if not isinstance(parts, list):
                raise AssertionError("expected parts list")
            file_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "file"]
            if not file_parts:
                raise AssertionError(f"expected file part, got: {parts!r}")
            url = file_parts[0].get("url")
            if not isinstance(url, str) or "%23" not in url:
                raise AssertionError(f"expected url with %23 encoding, got: {url!r}")
            content = payload.get("content")
            if not isinstance(content, str) or "content-from-weird-file" not in content:
                raise AssertionError("expected injected file content in rendered content")

            return ModelOutput(
                assistant_text="E2E_OFFLINE_SLASH_TOOL_OK",
                tool_calls=(),
                response_id="resp-sc-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineSlashCommandToolParts(unittest.IsolatedAsyncioTestCase):
    async def test_slash_command_tool_returns_parts_and_encoded_file_url(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            weird = root / "weird#name.txt"
            weird.write_text("content-from-weird-file", encoding="utf-8")

            cmd_dir = root / ".claude" / "commands"
            cmd_dir.mkdir(parents=True)
            (cmd_dir / "show.md").write_text("Here: @weird#name.txt\n", encoding="utf-8")

            provider = _SlashCommandToolProvider()
            opts = make_options_offline(root, provider=provider, allowed_tools=["SlashCommand", "Read", "List"])
            r = await openagentic_sdk.run(prompt="slash tool", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_SLASH_TOOL_OK")


if __name__ == "__main__":
    unittest.main()

