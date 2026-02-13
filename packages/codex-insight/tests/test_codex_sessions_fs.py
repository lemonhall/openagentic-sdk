from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_insight.db.codex_sessions import CodexSessionsFs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestCodexSessionsFs(unittest.TestCase):
    def test_recent_sessions_and_rollout_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sessions_dir = Path(td) / "sessions" / "2026" / "02" / "13"
            file1 = sessions_dir / "rollout-2026-02-13T00-00-00-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.jsonl"
            _write_jsonl(
                file1,
                [
                    {
                        "timestamp": "2026-02-13T00:00:01Z",
                        "type": "session_meta",
                        "payload": {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "timestamp": "2026-02-13T00:00:00Z", "cwd": "E:\\p1"},
                    },
                    {
                        "timestamp": "2026-02-13T00:00:02Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "hello world"}],
                        },
                    },
                ],
            )

            fs = CodexSessionsFs(str(Path(td) / "sessions"))
            self.assertTrue(fs.exists())
            stats = fs.stats()
            self.assertEqual(stats.session_count, 1)

            rec = fs.recent_sessions(limit=10)
            self.assertEqual(len(rec), 1)
            self.assertEqual(rec[0].session_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
            self.assertEqual(rec[0].title, "hello world")
            self.assertEqual(rec[0].cwd, "E:\\p1")

            rp = fs.rollout_path_for_session("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
            self.assertTrue(rp and rp.endswith(".jsonl"))

