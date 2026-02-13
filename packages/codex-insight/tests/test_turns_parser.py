from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_insight.parser.turns import load_turns


class TestTurnsParser(unittest.TestCase):
    def test_load_turns_filters_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout.jsonl"
            rows = [
                {
                    "timestamp": "2026-02-13T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "<environment_context>..."}],
                    },
                },
                {
                    "timestamp": "2026-02-13T00:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "task 1"}],
                    },
                },
                {
                    "timestamp": "2026-02-13T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "answer 1"}],
                    },
                },
            ]
            p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

            turns = load_turns(str(p), include_context_user_messages=False)
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0].user_text, "task 1")
            self.assertEqual(turns[0].assistant_text, "answer 1")

            turns2 = load_turns(str(p), include_context_user_messages=True)
            self.assertEqual(len(turns2), 2)

