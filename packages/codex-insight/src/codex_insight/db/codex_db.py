from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SessionRow:
    session_id: str
    title: str
    created_at: int | None
    updated_at: int | None
    token_count: int | None
    cwd: str | None
    rollout_path: str | None


@dataclass(frozen=True, slots=True)
class CodexStats:
    session_count: int
    token_sum: int | None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols: set[str] = set()
    for row in cur.fetchall():
        name: str | None = None
        try:
            if isinstance(row, sqlite3.Row):
                val = row["name"]
                name = val if isinstance(val, str) else None
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                val = row[1]
                name = val if isinstance(val, str) else None
        except Exception:
            name = None
        if name:
            cols.add(name)
    return cols


def _pick_first(existing: set[str], *names: str) -> str | None:
    for nm in names:
        if nm in existing:
            return nm
    return None


class CodexDb:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def exists(self) -> bool:
        return bool(self.db_path) and Path(self.db_path).exists()

    def stats(self) -> CodexStats:
        if not self.exists():
            return CodexStats(session_count=0, token_sum=None)
        conn = self._connect()
        try:
            cols = _table_columns(conn, "threads")
            token_col = _pick_first(cols, "token_count", "tokens", "total_tokens", "usage_tokens")
            session_count = int(conn.execute("SELECT COUNT(*) AS c FROM threads").fetchone()["c"])
            token_sum: int | None = None
            if token_col:
                row = conn.execute(f"SELECT SUM({token_col}) AS s FROM threads").fetchone()
                if row is not None:
                    val = row["s"]
                    if isinstance(val, int):
                        token_sum = val
                    elif isinstance(val, float):
                        token_sum = int(val)
            return CodexStats(session_count=session_count, token_sum=token_sum)
        finally:
            conn.close()

    def recent_sessions(self, limit: int = 50) -> list[SessionRow]:
        if not self.exists():
            return []
        limit = max(1, int(limit))
        conn = self._connect()
        try:
            cols = _table_columns(conn, "threads")
            id_col = _pick_first(cols, "id", "thread_id", "uuid")
            title_col = _pick_first(cols, "title", "name")
            created_col = _pick_first(cols, "created_at", "createdAt", "created", "ts_created")
            updated_col = _pick_first(cols, "updated_at", "updatedAt", "updated", "ts_updated", "last_updated_at")
            token_col = _pick_first(cols, "token_count", "tokens", "total_tokens", "usage_tokens")
            cwd_col = _pick_first(cols, "cwd", "workdir", "project_dir", "projectDir")
            rollout_col = _pick_first(cols, "rollout_path", "rolloutPath", "path", "transcript_path")

            if not id_col:
                raise RuntimeError("threads table has no id column (expected id/thread_id/uuid)")

            select_cols: list[str] = [id_col]
            for c in (title_col, created_col, updated_col, token_col, cwd_col, rollout_col):
                if c and c not in select_cols:
                    select_cols.append(c)

            order_col = updated_col or created_col or id_col
            q = f"SELECT {', '.join(select_cols)} FROM threads ORDER BY {order_col} DESC LIMIT ?"
            cur = conn.execute(q, (limit,))

            out: list[SessionRow] = []
            for r in cur.fetchall():
                d: Mapping[str, Any] = dict(r) if isinstance(r, sqlite3.Row) else r
                out.append(
                    SessionRow(
                        session_id=str(d.get(id_col, "")),
                        title=str(d.get(title_col, "")) if title_col else "",
                        created_at=int(d.get(created_col)) if created_col and d.get(created_col) is not None else None,
                        updated_at=int(d.get(updated_col)) if updated_col and d.get(updated_col) is not None else None,
                        token_count=int(d.get(token_col)) if token_col and d.get(token_col) is not None else None,
                        cwd=str(d.get(cwd_col)) if cwd_col and d.get(cwd_col) is not None else None,
                        rollout_path=str(d.get(rollout_col)) if rollout_col and d.get(rollout_col) is not None else None,
                    )
                )
            return out
        finally:
            conn.close()

    def sessions_by_cwd(self, limit: int = 20) -> list[tuple[str, int]]:
        if not self.exists():
            return []
        limit = max(1, int(limit))
        conn = self._connect()
        try:
            cols = _table_columns(conn, "threads")
            cwd_col = _pick_first(cols, "cwd", "workdir", "project_dir", "projectDir")
            if not cwd_col:
                return []
            q = f"""
                SELECT {cwd_col} AS cwd, COUNT(*) AS c
                FROM threads
                WHERE {cwd_col} IS NOT NULL AND TRIM({cwd_col}) != ''
                GROUP BY {cwd_col}
                ORDER BY c DESC
                LIMIT ?
            """
            cur = conn.execute(q, (limit,))
            out: list[tuple[str, int]] = []
            for r in cur.fetchall():
                cwd = r["cwd"]
                c = r["c"]
                if isinstance(cwd, str) and isinstance(c, int):
                    out.append((cwd, c))
            return out
        finally:
            conn.close()
