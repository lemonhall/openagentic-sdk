from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from ..events import AssistantMessage, Event, Result, SessionRedo, SessionSetHead, SessionUndo, UserMessage
from ..serialization import event_to_dict


@dataclass(frozen=True, slots=True)
class EditableSessionMessage:
    seq: int
    role: str
    text: str


def _max_seq(events: list[Event]) -> int:
    seqs = [getattr(event, "seq", None) for event in events]
    nums = [seq for seq in seqs if isinstance(seq, int) and seq > 0]
    if nums:
        return max(nums)
    return len(events)


def _effective_head_seq(events: list[Event]) -> int:
    head = _max_seq(events)
    undo_stack: list[int] = []
    redo_stack: list[int] = []

    for event in events:
        if isinstance(event, SessionSetHead):
            target = int(getattr(event, "head_seq", 0) or 0)
            if target <= 0:
                continue
            undo_stack.append(head)
            head = target
            redo_stack.clear()
            continue
        if isinstance(event, SessionUndo):
            if undo_stack:
                redo_stack.append(head)
                head = undo_stack.pop()
            continue
        if isinstance(event, SessionRedo):
            if redo_stack:
                undo_stack.append(head)
                head = redo_stack.pop()
            continue

    return head


def _filter_to_head(events: list[Event]) -> list[Event]:
    head = _effective_head_seq(events)
    out: list[Event] = []
    for event in events:
        if isinstance(event, (SessionSetHead, SessionUndo, SessionRedo)):
            continue
        seq = getattr(event, "seq", None)
        if isinstance(seq, int) and seq > 0:
            if seq <= head:
                out.append(event)
            continue
        out.append(event)
    return out


def session_fingerprint_from_path(path: Path) -> str:
    if not path.exists():
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def list_editable_messages(events: list[Event]) -> list[EditableSessionMessage]:
    out: list[EditableSessionMessage] = []
    for event in _filter_to_head(events):
        seq = getattr(event, "seq", None)
        if not isinstance(seq, int) or seq <= 0:
            continue
        if isinstance(event, UserMessage):
            out.append(EditableSessionMessage(seq=seq, role="user", text=event.text))
            continue
        if isinstance(event, AssistantMessage):
            out.append(EditableSessionMessage(seq=seq, role="assistant", text=event.text))
    return out


def apply_message_text_edit(events: list[Event], *, seq: int, new_text: str) -> tuple[list[Event], bool]:
    editable_by_seq = {msg.seq: msg for msg in list_editable_messages(events)}
    target = editable_by_seq.get(seq)
    if target is None:
        raise ValueError(f"editable message not found for seq={seq}")

    if target.text == new_text:
        return list(events), False

    changed = False
    out: list[Event] = []
    for event in events:
        event_seq = getattr(event, "seq", None)
        if event_seq == seq and isinstance(event, UserMessage):
            out.append(replace(event, text=new_text))
            changed = True
            continue
        if event_seq == seq and isinstance(event, AssistantMessage):
            out.append(replace(event, text=new_text))
            changed = True
            continue
        if isinstance(event, Result) and getattr(event, "response_id", None) is not None:
            out.append(replace(event, response_id=None))
            continue
        out.append(event)

    return out, changed


def render_events_jsonl(events: list[Event]) -> str:
    return "".join(json.dumps(event_to_dict(event), ensure_ascii=False, separators=(",", ":")) + "\n" for event in events)


def render_transcript_jsonl(events: list[Event]) -> str:
    lines: list[str] = []
    for event in events:
        if isinstance(event, UserMessage):
            entry = {"seq": event.seq, "ts": event.ts, "role": "user", "text": event.text}
        elif isinstance(event, AssistantMessage):
            entry = {"seq": event.seq, "ts": event.ts, "role": "assistant", "text": event.text}
        else:
            continue
        lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return "".join(lines)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
