from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..db.cache_db import CacheDb
from ..parser.turns import Turn


@dataclass(frozen=True, slots=True)
class WorkbenchSnapshot:
    codex_session_id: str
    rollout_path: str | None
    include_context_user_messages: bool
    turns: list[Turn]
    selected_turn_indices: list[int]


def _safe_name(s: str, *, limit: int = 80) -> str:
    s2 = re.sub(r"[^A-Za-z0-9_.-]+", "_", (s or "").strip()) or "untitled"
    return s2[:limit].strip("._-") or "untitled"


_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s]+)"), r"\1***"),
    (re.compile(r"(?i)\b(sk-[a-z0-9]{16,})\b"), "***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*['\"]?([^\s'\";]+)"
        ),
        r"\1=***",
    ),
    (re.compile(r"-----BEGIN [^-]+ PRIVATE KEY-----[\s\S]+?-----END [^-]+ PRIVATE KEY-----"), "***"),
]


def _redact(text: str) -> str:
    s = text or ""
    for pat, repl in _REDACT_PATTERNS:
        s = pat.sub(repl, s)
    return s


def _clip(text: str, limit: int) -> str:
    s = (text or "").replace("\r\n", "\n").strip()
    return s if len(s) <= limit else (s[:limit] + "…(truncated)")


class InsightGetSnapshot:
    name = "InsightGetSnapshot"
    description = "Get a read-only snapshot for the currently viewed Codex session (turns, selection, rollout path)."

    def __init__(self, snapshot: WorkbenchSnapshot) -> None:
        self._snapshot = snapshot

    async def run(self, tool_input: Mapping[str, Any], ctx: Any) -> Any:
        snap = self._snapshot
        preview_limit = int(tool_input.get("preview_limit") or 160)
        turns = [
            {
                "index": t.index,
                "user_preview": _clip(_redact(t.user_text), preview_limit),
                "assistant_preview": _clip(_redact(t.assistant_text), preview_limit),
            }
            for t in snap.turns
        ]
        return {
            "codex_session_id": snap.codex_session_id,
            "rollout_path": snap.rollout_path or "",
            "include_context_user_messages": bool(snap.include_context_user_messages),
            "turn_count": len(snap.turns),
            "selected_turn_indices": list(snap.selected_turn_indices),
            "turns": turns,
        }


class InsightGetTurn:
    name = "InsightGetTurn"
    description = "Get full user and assistant(final) text for a given turn index in this session."

    def __init__(self, snapshot: WorkbenchSnapshot) -> None:
        self._snapshot = snapshot

    async def run(self, tool_input: Mapping[str, Any], ctx: Any) -> Any:
        idx = int(tool_input.get("index") or 0)
        for t in self._snapshot.turns:
            if t.index == idx:
                return {
                    "index": t.index,
                    "user_text": _redact(t.user_text or ""),
                    "assistant_text": _redact(t.assistant_text or ""),
                }
        return {"error": f"turn {idx} not found"}


class InsightReadRolloutTail:
    name = "InsightReadRolloutTail"
    description = "Read the tail of the rollout jsonl file for this session (redacted and truncated)."

    def __init__(self, snapshot: WorkbenchSnapshot) -> None:
        self._snapshot = snapshot

    async def run(self, tool_input: Mapping[str, Any], ctx: Any) -> Any:
        if not self._snapshot.rollout_path:
            return {"error": "rollout_path not available"}
        max_lines = int(tool_input.get("max_lines") or 60)
        contains = tool_input.get("contains")
        contains_s = str(contains) if isinstance(contains, (str, int, float)) else None

        p = Path(self._snapshot.rollout_path)
        if not p.exists() or not p.is_file():
            return {"error": "rollout file not found"}
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            return {"error": f"failed to read rollout: {e}"}

        tail = lines[-max_lines:] if max_lines > 0 else lines
        if contains_s:
            tail = [ln for ln in tail if contains_s in ln]
        redacted = [_clip(_redact(ln), 2000) for ln in tail]
        return {"rollout_path": str(p), "lines": redacted, "line_count": len(redacted)}


class InsightGetCachedReview:
    name = "InsightGetCachedReview"
    description = "Get cached AI review for (scope, selection). scope in {turn, selection, session}."

    def __init__(self, snapshot: WorkbenchSnapshot, cache: CacheDb) -> None:
        self._snapshot = snapshot
        self._cache = cache

    async def run(self, tool_input: Mapping[str, Any], ctx: Any) -> Any:
        scope = str(tool_input.get("scope") or "session").strip()
        selection = str(tool_input.get("selection") or "all").strip()
        if scope not in ("turn", "selection", "session"):
            scope = "session"
        if scope == "session":
            selection = "all"
        cached = self._cache.get_review_scoped(session_id=self._snapshot.codex_session_id, scope=scope, selection=selection)
        if cached is None:
            return {"found": False, "scope": scope, "selection": selection}
        return {
            "found": True,
            "scope": scope,
            "selection": selection,
            "model": cached.model,
            "analyzed_at": cached.analyzed_at,
            "review_markdown": cached.review_markdown,
        }


class InsightWriteArtifact:
    name = "InsightWriteArtifact"
    description = "Write an artifact markdown file under ~/.codex-insight/artifacts/<session>/ (redacted)."

    def __init__(self, snapshot: WorkbenchSnapshot, cache: CacheDb) -> None:
        self._snapshot = snapshot
        self._cache = cache

    async def run(self, tool_input: Mapping[str, Any], ctx: Any) -> Any:
        kind = _safe_name(str(tool_input.get("kind") or "artifact"), limit=24)
        title = str(tool_input.get("title") or "artifact").strip() or "artifact"
        content_md = str(tool_input.get("content_md") or "").strip()
        if not content_md:
            return {"error": "content_md is empty"}

        now = int(time.time())
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
        base = Path.home() / ".codex-insight" / "artifacts" / _safe_name(self._snapshot.codex_session_id, limit=64)
        base.mkdir(parents=True, exist_ok=True)

        filename = tool_input.get("filename")
        if isinstance(filename, str) and filename.strip():
            fname = _safe_name(filename.strip(), limit=80)
            if not fname.lower().endswith(".md"):
                fname = f"{fname}.md"
        else:
            fname = f"{ts}-{kind}-{_safe_name(title, limit=48)}.md"

        path = base / fname
        text = _redact(content_md)
        path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        rec = self._cache.insert_artifact(
            codex_session_id=self._snapshot.codex_session_id,
            kind=kind,
            title=title,
            content_md=text,
            saved_path=str(path),
        )
        return {"saved_path": str(path), "artifact_id": rec.artifact_id, "kind": kind, "title": title}


def build_workbench_tools(*, snapshot: WorkbenchSnapshot, cache: CacheDb) -> list[Any]:
    return [
        InsightGetSnapshot(snapshot),
        InsightGetTurn(snapshot),
        InsightReadRolloutTail(snapshot),
        InsightGetCachedReview(snapshot, cache),
        InsightWriteArtifact(snapshot, cache),
    ]
