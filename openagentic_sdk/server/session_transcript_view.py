from __future__ import annotations

import json
from typing import Any

from ..sessions.paths import events_path
from ..sessions.store import FileSessionStore


def build_session_transcript(
    *,
    store: FileSessionStore,
    session_id: str,
    source: str,
    default_agent_name: str | None = None,
) -> dict[str, Any]:
    session_dir = store.session_dir(session_id)
    if not session_dir.exists():
        raise FileNotFoundError(session_id)
    metadata = store.read_metadata(session_id)
    agent_name = metadata.get("agent_name") if isinstance(metadata.get("agent_name"), str) else None
    messages = _read_event_messages(events_path(store.root_dir, session_id))
    return {
        "session_id": session_id,
        "agent_name": agent_name or (default_agent_name or ""),
        "source": source,
        "messages": messages,
    }


def _read_event_messages(path):
    if not path.exists():
        return []
    messages: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            continue
        event_type = obj.get("type")
        if event_type == "user.message":
            role = "user"
        elif event_type == "assistant.message":
            role = "assistant"
        else:
            continue
        text = obj.get("text") if isinstance(obj.get("text"), str) else ""
        message: dict[str, Any] = {
            "role": role,
            "text": text,
        }
        seq = obj.get("seq")
        if isinstance(seq, int):
            message["seq"] = seq
        ts = obj.get("ts")
        if isinstance(ts, (int, float)):
            message["ts"] = ts
        messages.append(message)
    return messages
