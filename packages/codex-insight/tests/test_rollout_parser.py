from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_insight.parser.rollout import load_rollout_messages


class TestRolloutParser(unittest.TestCase):
    def test_load_codex_cli_sessions_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout.jsonl"
            rows = [
                {"timestamp": "2026-02-13T00:00:01Z", "type": "session_meta", "payload": {"id": "s1", "cwd": "E:\\x"}},
                {
                    "timestamp": "2026-02-13T00:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hi"}],
                    },
                },
                {
                    "timestamp": "2026-02-13T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hello"}],
                    },
                },
                {
                    "timestamp": "2026-02-13T00:00:04Z",
                    "type": "response_item",
                    "payload": {"type": "function_call", "name": "Read", "arguments": {"path": "x"}},
                },
            ]
            p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

            msgs = load_rollout_messages(str(p))
            self.assertGreaterEqual(len(msgs), 3)
            self.assertEqual(msgs[0]["role"], "user")
            self.assertEqual(msgs[0]["content"], "hi")
            self.assertEqual(msgs[1]["role"], "assistant")
            self.assertEqual(msgs[1]["content"], "hello")
            self.assertEqual(msgs[2]["role"], "tool")

