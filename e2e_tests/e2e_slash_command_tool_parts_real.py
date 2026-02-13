from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESlashCommandToolPartsReal(unittest.IsolatedAsyncioTestCase):
    async def test_slash_command_tool_emits_parts_and_injects_rendered_content(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            token = f"SLASH_TOOL_TOKEN_{uuid.uuid4().hex}"

            weird = root / "weird#name.txt"
            weird.write_text(token, encoding="utf-8")

            cmd_dir = root / ".opencode" / "commands"
            cmd_dir.mkdir(parents=True)
            (cmd_dir / "show.md").write_text("Use this file:\n@weird#name.txt\n", encoding="utf-8")

            opts = make_options(root, allowed_tools=["SlashCommand", "Read", "List"])

            prompt = (
                "You MUST call the SlashCommand tool with name='show' and args=''.\n"
                "After the tool returns, reply with exactly: SHOW_OK\n"
                "Do not guess."
            )

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            tool_results = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "is_error", False) is False
            ]
            slash_out = next((o for o in tool_results if isinstance(o, dict) and o.get("name") == "show" and o.get("parts")), None)
            self.assertIsInstance(slash_out, dict)
            parts = slash_out.get("parts")
            self.assertIsInstance(parts, list)
            file_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "file"]
            self.assertTrue(file_parts)
            url = file_parts[0].get("url")
            self.assertIsInstance(url, str)
            self.assertIn("%23", url)
            self.assertIn(token, str(slash_out.get("content") or ""))

            final_texts = [getattr(e, "final_text", "") for e in events if getattr(e, "type", None) == "result"]
            self.assertTrue(final_texts)
            self.assertEqual(final_texts[-1].strip().rstrip("."), "SHOW_OK")


if __name__ == "__main__":
    unittest.main()
