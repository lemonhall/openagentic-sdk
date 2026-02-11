from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _EchoUserPromptProvider:
    name = "offline-slash-direct"

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput

        items = list(input)
        user_items = [x for x in items if isinstance(x, dict) and x.get("role") == "user" and isinstance(x.get("content"), str)]
        last_user = user_items[-1]["content"] if user_items else ""

        if "/show" in last_user:
            raise AssertionError("expected slash command to be expanded before model call")
        if "hello-from-file" not in last_user:
            raise AssertionError(f"expected injected file content, got: {last_user!r}")

        return ModelOutput(
            assistant_text="E2E_OFFLINE_SLASH_OK",
            tool_calls=(),
            response_id="resp-slash-1",
            provider_metadata={"protocol": "responses"},
        )


class TestE2EOfflineSlashCommandDirectExec(unittest.IsolatedAsyncioTestCase):
    async def test_user_slash_command_is_expanded_and_injects_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()  # mark worktree root for @file resolution
            (root / "a.txt").write_text("hello-from-file", encoding="utf-8")

            cmd_dir = root / ".claude" / "commands"
            cmd_dir.mkdir(parents=True)
            (cmd_dir / "show.md").write_text("Show this file:\n@a.txt\n", encoding="utf-8")

            opts = make_options_offline(root, provider=_EchoUserPromptProvider(), allowed_tools=["Read", "List"])
            r = await openagentic_sdk.run(prompt="/show", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_SLASH_OK")


if __name__ == "__main__":
    unittest.main()

