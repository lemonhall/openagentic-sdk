from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from codex_insight.db.cache_db import CacheDb


class TestCacheDb(unittest.TestCase):
    def test_workbench_chat_mapping_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "cache.sqlite"
            cache = CacheDb(path=db_path)

            self.assertIsNone(cache.get_workbench_chat(codex_session_id="sess1"))

            rec = cache.get_or_create_workbench_chat(codex_session_id="sess1", create_oa_session_id=lambda: "0" * 32)
            self.assertEqual(rec.codex_session_id, "sess1")
            self.assertEqual(rec.oa_session_id, "0" * 32)

            rec2 = cache.get_workbench_chat(codex_session_id="sess1")
            self.assertIsNotNone(rec2)
            assert rec2 is not None
            self.assertEqual(rec2.oa_session_id, "0" * 32)

            cache.touch_workbench_chat(codex_session_id="sess1")

            art = cache.insert_artifact(
                codex_session_id="sess1",
                kind="skill",
                title="t",
                content_md="# hi\n",
                saved_path=str(Path(td) / "a.md"),
            )
            self.assertEqual(art.codex_session_id, "sess1")
            self.assertEqual(art.kind, "skill")
            self.assertTrue(art.saved_path.endswith("a.md"))

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT COUNT(1) FROM artifacts").fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row[0]), 1)
