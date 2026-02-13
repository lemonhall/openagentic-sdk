from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_rollout_messages(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []

    out: list[dict[str, Any]] = []
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
                # Support both:
                # - plain chat jsonl: {role, content}
                # - Codex CLI sessions jsonl: {timestamp, type, payload}
                msgs = _coerce_messages(obj)
                if msgs:
                    out.extend(msgs)
    except OSError:
        return []
    return out


def _coerce_messages(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict):
        return []

    # Plain format.
    role = obj.get("role")
    content = obj.get("content")
    if isinstance(role, str) and isinstance(content, str):
        return [{"role": role, "content": content}]

    msg = obj.get("message")
    if isinstance(msg, dict):
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(role, str) and isinstance(content, str):
            return [{"role": role, "content": content}]

    # Some transcripts use "text" field
    role = obj.get("role")
    text = obj.get("text")
    if isinstance(role, str) and isinstance(text, str):
        return [{"role": role, "content": text}]

    # Codex CLI sessions jsonl.
    typ = obj.get("type")
    payload = obj.get("payload")
    if isinstance(typ, str) and isinstance(payload, dict):
        # Messages.
        if typ == "response_item" and payload.get("type") == "message":
            role = payload.get("role")
            content = payload.get("content")
            text2 = _extract_text_from_content(content)
            if isinstance(role, str) and text2:
                return [{"role": role, "content": text2}]
        # Tool calls / outputs (show as tool role).
        if typ == "response_item" and payload.get("type") in ("function_call", "function_call_output"):
            name = payload.get("name")
            if isinstance(name, str) and name:
                if payload.get("type") == "function_call":
                    args = payload.get("arguments")
                    return [{"role": "tool", "content": f"call {name} args={_short(args)}"}]
                out = payload.get("output")
                return [{"role": "tool", "content": f"result {name} output={_short(out)}"}]

    return []


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


def _short(obj: Any, limit: int = 200) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(obj)
    s = s.replace("\n", " ").strip()
    return s if len(s) <= limit else (s[:limit] + "…")
