from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Turn:
    index: int
    user_text: str
    assistant_text: str


def load_turns(
    path: str,
    *,
    include_context_user_messages: bool = False,
) -> list[Turn]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []

    messages: list[tuple[str, str]] = []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = _extract_message(obj)
                if msg is None:
                    continue
                role, text = msg
                if role not in ("user", "assistant"):
                    continue
                if role == "user" and not include_context_user_messages and _looks_like_context_blob(text):
                    continue
                messages.append((role, text))
    except OSError:
        return []

    turns: list[Turn] = []
    current_user: str | None = None
    current_assistant: str = ""

    def flush() -> None:
        nonlocal current_user, current_assistant
        if current_user is None:
            return
        idx = len(turns) + 1
        turns.append(Turn(index=idx, user_text=current_user, assistant_text=current_assistant))
        current_user = None
        current_assistant = ""

    for role, text in messages:
        if role == "user":
            flush()
            current_user = text
            current_assistant = ""
        elif role == "assistant":
            if current_user is None:
                continue
            current_assistant = text

    flush()
    return turns


def _extract_message(obj: Any) -> tuple[str, str] | None:
    """Extract (role, text) from either a plain transcript or Codex CLI sessions jsonl."""
    if not isinstance(obj, dict):
        return None

    # Plain jsonl: {role, content}
    role = obj.get("role")
    content = obj.get("content")
    if isinstance(role, str) and isinstance(content, str) and content.strip():
        return role.strip(), content.strip()

    typ = obj.get("type")
    payload = obj.get("payload")
    if isinstance(typ, str) and isinstance(payload, dict):
        if typ == "response_item" and payload.get("type") == "message":
            role = payload.get("role")
            content = payload.get("content")
            text = _extract_text_from_content(content)
            if isinstance(role, str) and text:
                return role.strip(), text
    return None


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


def _looks_like_context_blob(text: str) -> bool:
    s = text.lstrip()
    if s.startswith("<environment_context>"):
        return True
    if s.startswith("<permissions instructions>"):
        return True
    if s.startswith("<collaboration_mode>"):
        return True
    if s.startswith("# AGENTS.md instructions"):
        return True
    if s.startswith("<INSTRUCTIONS>"):
        return True
    if s.startswith("--- project-doc ---"):
        return True
    if s.startswith("<skill>"):
        return True
    return False

