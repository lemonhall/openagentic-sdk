from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .codex_db import CodexStats, SessionRow

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _parse_iso8601_to_epoch_s(value: str) -> int | None:
    s = value.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class CodexSessionsFs:
    sessions_dir: Path

    _id_to_path: dict[str, Path]

    def __init__(self, sessions_dir: str) -> None:
        p = Path(sessions_dir) if sessions_dir else Path()
        object.__setattr__(self, "sessions_dir", p)
        object.__setattr__(self, "_id_to_path", {})

    def exists(self) -> bool:
        return self.sessions_dir.exists() and self.sessions_dir.is_dir()

    def stats(self) -> CodexStats:
        if not self.exists():
            return CodexStats(session_count=0, token_sum=None)
        try:
            n = sum(1 for _ in self.sessions_dir.rglob("*.jsonl"))
        except Exception:
            n = 0
        return CodexStats(session_count=n, token_sum=None)

    def sessions_by_cwd(self, limit: int = 20) -> list[tuple[str, int]]:
        if not self.exists():
            return []
        limit = max(1, int(limit))
        counts: dict[str, int] = {}
        for path in self._iter_rollout_files_sorted():
            meta = self._read_session_meta(path)
            cwd = meta.get("cwd")
            if not isinstance(cwd, str) or not cwd.strip():
                continue
            counts[cwd] = counts.get(cwd, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    def recent_sessions(self, limit: int = 50) -> list[SessionRow]:
        if not self.exists():
            return []
        limit = max(1, int(limit))
        out: list[SessionRow] = []
        for path in self._iter_rollout_files_sorted()[:limit]:
            meta = self._read_session_meta(path)
            session_id = meta.get("id")
            if not isinstance(session_id, str) or not session_id:
                session_id = self._infer_session_id_from_filename(path.name) or path.stem
            self._id_to_path[session_id] = path
            created_at = None
            ts = meta.get("timestamp")
            if isinstance(ts, str):
                created_at = _parse_iso8601_to_epoch_s(ts)

            title = self._read_first_user_title(path)
            cwd = meta.get("cwd") if isinstance(meta.get("cwd"), str) else None
            out.append(
                SessionRow(
                    session_id=session_id,
                    title=title,
                    created_at=created_at,
                    updated_at=int(path.stat().st_mtime),
                    token_count=None,
                    cwd=cwd,
                    rollout_path=str(path),
                )
            )
        return out

    def rollout_path_for_session(self, session_id: str) -> str | None:
        if not session_id:
            return None
        p = self._id_to_path.get(session_id)
        if p is not None and p.exists():
            return str(p)
        if not self.exists():
            return None

        # Fast path: filename contains id.
        try:
            for path in self.sessions_dir.rglob(f"*{session_id}*.jsonl"):
                self._id_to_path[session_id] = path
                return str(path)
        except Exception:
            return None
        return None

    def _iter_rollout_files_sorted(self) -> list[Path]:
        try:
            files = [p for p in self.sessions_dir.rglob("*.jsonl") if p.is_file()]
        except Exception:
            return []
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def _infer_session_id_from_filename(self, name: str) -> str | None:
        m = _UUID_RE.search(name)
        if m:
            return m.group(0)
        return None

    def _read_session_meta(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for _ in range(50):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get("type") == "session_meta":
                        payload = obj.get("payload")
                        if isinstance(payload, dict):
                            return dict(payload)
        except Exception:
            return {}
        return {}

    def _read_first_user_title(self, path: Path) -> str:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for _ in range(300):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if not isinstance(obj, dict) or obj.get("type") != "response_item":
                        continue
                    payload = obj.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") != "message" or payload.get("role") != "user":
                        continue
                    # Prefer plaintext content when available.
                    content = payload.get("content")
                    text = _extract_text_from_content(content)
                    if text:
                        return text[:80]
                    summary = payload.get("summary")
                    if isinstance(summary, str) and summary.strip():
                        return summary.strip()[:80]
        except Exception:
            return ""
        return ""


def _extract_text_from_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        typ = part.get("type")
        if typ in ("input_text", "output_text"):
            txt = part.get("text")
            if isinstance(txt, str) and txt.strip():
                parts.append(txt.strip())
    return "\n".join(parts).strip()

