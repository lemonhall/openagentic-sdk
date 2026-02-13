from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CachedReview:
    review_id: str
    session_id: str
    scope: str
    selection: str
    review_markdown: str
    model: str
    analyzed_at: int


@dataclass(frozen=True, slots=True)
class WorkbenchChat:
    codex_session_id: str
    oa_session_id: str
    created_at: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    codex_session_id: str
    kind: str
    title: str
    content_md: str
    saved_path: str
    created_at: int


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

    def _conn(self):
        return closing(self._connect())

    def ensure_schema(self) -> None:
        with self._conn() as conn:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    review_markdown TEXT NOT NULL,
                    model TEXT NOT NULL,
                    analyzed_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workbench_chats (
                    codex_session_id TEXT PRIMARY KEY,
                    oa_session_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    codex_session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_md TEXT NOT NULL,
                    saved_path TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def get_review(self, session_id: str) -> CachedReview | None:
        self.ensure_schema()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT session_id, review_markdown, model, analyzed_at FROM session_reviews WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return CachedReview(
                review_id=str(row["session_id"]),
                session_id=str(row["session_id"]),
                scope="session",
                selection="all",
                review_markdown=str(row["review_markdown"]),
                model=str(row["model"]),
                analyzed_at=int(row["analyzed_at"]),
            )

    def upsert_review(self, *, session_id: str, review_markdown: str, model: str) -> None:
        self.ensure_schema()
        now = int(time.time())
        with self._conn() as conn:
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

    def get_review_scoped(self, *, session_id: str, scope: str, selection: str) -> CachedReview | None:
        self.ensure_schema()
        review_id = f"{session_id}:{scope}:{selection}"
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT review_id, session_id, scope, selection, review_markdown, model, analyzed_at
                FROM reviews
                WHERE review_id=?
                """,
                (review_id,),
            ).fetchone()
            if row is None:
                return None
            return CachedReview(
                review_id=str(row["review_id"]),
                session_id=str(row["session_id"]),
                scope=str(row["scope"]),
                selection=str(row["selection"]),
                review_markdown=str(row["review_markdown"]),
                model=str(row["model"]),
                analyzed_at=int(row["analyzed_at"]),
            )

    def upsert_review_scoped(self, *, session_id: str, scope: str, selection: str, review_markdown: str, model: str) -> None:
        self.ensure_schema()
        review_id = f"{session_id}:{scope}:{selection}"
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reviews (review_id, session_id, scope, selection, review_markdown, model, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET
                    review_markdown=excluded.review_markdown,
                    model=excluded.model,
                    analyzed_at=excluded.analyzed_at
                """,
                (review_id, session_id, scope, selection, review_markdown, model, now),
            )
            conn.commit()

    def get_or_create_workbench_chat(self, *, codex_session_id: str, create_oa_session_id: Any) -> WorkbenchChat:
        """Return the mapped OA session id for this Codex session, creating one if missing.

        `create_oa_session_id` is a callable that returns a 32-hex OA session id.
        """
        self.ensure_schema()
        now = int(time.time())
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT codex_session_id, oa_session_id, created_at, updated_at
                FROM workbench_chats
                WHERE codex_session_id=?
                """,
                (codex_session_id,),
            ).fetchone()
            if row is not None:
                return WorkbenchChat(
                    codex_session_id=str(row["codex_session_id"]),
                    oa_session_id=str(row["oa_session_id"]),
                    created_at=int(row["created_at"]),
                    updated_at=int(row["updated_at"]),
                )

            oa_session_id = str(create_oa_session_id())
            conn.execute(
                """
                INSERT INTO workbench_chats (codex_session_id, oa_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (codex_session_id, oa_session_id, now, now),
            )
            conn.commit()
            return WorkbenchChat(codex_session_id=codex_session_id, oa_session_id=oa_session_id, created_at=now, updated_at=now)

    def get_workbench_chat(self, *, codex_session_id: str) -> WorkbenchChat | None:
        self.ensure_schema()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT codex_session_id, oa_session_id, created_at, updated_at
                FROM workbench_chats
                WHERE codex_session_id=?
                """,
                (codex_session_id,),
            ).fetchone()
            if row is None:
                return None
            return WorkbenchChat(
                codex_session_id=str(row["codex_session_id"]),
                oa_session_id=str(row["oa_session_id"]),
                created_at=int(row["created_at"]),
                updated_at=int(row["updated_at"]),
            )

    def touch_workbench_chat(self, *, codex_session_id: str) -> None:
        self.ensure_schema()
        now = int(time.time())
        with self._conn() as conn:
            conn.execute("UPDATE workbench_chats SET updated_at=? WHERE codex_session_id=?", (now, codex_session_id))
            conn.commit()

    def insert_artifact(
        self,
        *,
        codex_session_id: str,
        kind: str,
        title: str,
        content_md: str,
        saved_path: str,
    ) -> ArtifactRecord:
        self.ensure_schema()
        now = int(time.time())
        artifact_id = uuid4().hex
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (artifact_id, codex_session_id, kind, title, content_md, saved_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, codex_session_id, kind, title, content_md, saved_path, now),
            )
            conn.commit()
        return ArtifactRecord(
            artifact_id=artifact_id,
            codex_session_id=codex_session_id,
            kind=kind,
            title=title,
            content_md=content_md,
            saved_path=saved_path,
            created_at=now,
        )
