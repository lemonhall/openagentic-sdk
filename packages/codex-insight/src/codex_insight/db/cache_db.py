from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CachedReview:
    session_id: str
    review_markdown: str
    model: str
    analyzed_at: int


def default_cache_db_path() -> Path:
    return Path.home() / ".codex-insight" / "cache.sqlite"


class CacheDb:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_cache_db_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_reviews (
                    session_id TEXT PRIMARY KEY,
                    review_markdown TEXT NOT NULL,
                    model TEXT NOT NULL,
                    analyzed_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def get_review(self, session_id: str) -> CachedReview | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id, review_markdown, model, analyzed_at FROM session_reviews WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return CachedReview(
                session_id=str(row["session_id"]),
                review_markdown=str(row["review_markdown"]),
                model=str(row["model"]),
                analyzed_at=int(row["analyzed_at"]),
            )

    def upsert_review(self, *, session_id: str, review_markdown: str, model: str) -> None:
        self.ensure_schema()
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_reviews (session_id, review_markdown, model, analyzed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    review_markdown=excluded.review_markdown,
                    model=excluded.model,
                    analyzed_at=excluded.analyzed_at
                """,
                (session_id, review_markdown, model, now),
            )
            conn.commit()

