from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from codex_insight.db.codex_db import CodexDb


class TestCodexDb(unittest.TestCase):
    def test_stats_and_recent_sessions_with_minimal_schema(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "state_5.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at INTEGER,
                    updated_at INTEGER,
                    token_count INTEGER,
                    cwd TEXT,
                    rollout_path TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO threads (id, title, created_at, updated_at, token_count, cwd, rollout_path) VALUES (?,?,?,?,?,?,?)",
                ("t1", "hello", 1, 2, 10, "C:/p", "C:/x.jsonl"),
            )
            conn.execute(
                "INSERT INTO threads (id, title, created_at, updated_at, token_count, cwd, rollout_path) VALUES (?,?,?,?,?,?,?)",
                ("t2", "world", 3, 4, 5, "C:/p", ""),
            )
            conn.commit()
            conn.close()

            db = CodexDb(db_path)
            self.assertTrue(db.exists())
            st = db.stats()
            self.assertEqual(st.session_count, 2)
            self.assertEqual(st.token_sum, 15)

            rows = db.recent_sessions(limit=10)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].session_id, "t2")
            self.assertEqual(rows[1].session_id, "t1")

            bycwd = db.sessions_by_cwd(limit=10)
            self.assertEqual(bycwd, [("C:/p", 2)])

