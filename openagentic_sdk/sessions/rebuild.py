from __future__ import annotations

import json
from typing import Any, Mapping

from ..compaction import COMPACTION_MARKER_QUESTION
from ..events import (
    AssistantMessage,
    Event,
    SessionRedo,
    SessionSetHead,
    SessionUndo,
    ToolOutputCompacted,
    ToolResult,
    ToolUse,
    UserCompaction,
    UserMessage,
)

_TOOL_OUTPUT_PLACEHOLDER = "[Old tool result content cleared]"


def _tool_result_content(event: ToolResult) -> Any:
    if not getattr(event, "is_error", False):
        return event.output
    return {
        "is_error": True,
        "error_type": getattr(event, "error_type", None),
        "error_message": getattr(event, "error_message", None),
        "output": event.output,
    }


def _filter_to_latest_summary_pivot(events: list[Event]) -> list[Event]:
    last_summary_idx: int | None = None
    for i, e in enumerate(events):
        if isinstance(e, AssistantMessage) and bool(getattr(e, "is_summary", False)):
            last_summary_idx = i
    if last_summary_idx is None:
        return events
    return events[last_summary_idx:]


def _max_seq(events: list[Event]) -> int:
    seqs = [getattr(e, "seq", None) for e in events]
    nums = [s for s in seqs if isinstance(s, int) and s > 0]
    if nums:
        return max(nums)
    # Back-compat: logs without seq.
    return len(events)


def _effective_head_seq(events: list[Event]) -> int:
    """Compute the effective head pointer after applying session control events."""

    head = _max_seq(events)
    undo_stack: list[int] = []
    redo_stack: list[int] = []

    for e in events:
        if isinstance(e, SessionSetHead):
            target = int(getattr(e, "head_seq", 0) or 0)
            if target <= 0:
                continue
            undo_stack.append(head)
            head = target
            redo_stack.clear()
            continue
        if isinstance(e, SessionUndo):
            if undo_stack:
                redo_stack.append(head)
                head = undo_stack.pop()
            continue
        if isinstance(e, SessionRedo):
            if redo_stack:
                undo_stack.append(head)
                head = redo_stack.pop()
            continue

    return head


def _filter_to_head(events: list[Event]) -> list[Event]:
    head = _effective_head_seq(events)
    out: list[Event] = []
    for e in events:
        if isinstance(e, (SessionSetHead, SessionUndo, SessionRedo)):
            continue
        seq = getattr(e, "seq", None)
        if isinstance(seq, int) and seq > 0:
            if seq <= head:
                out.append(e)
            continue
        # Back-compat: include unknown-seq events.
        out.append(e)
    return out


def _collect_compacted_tool_ids(events: list[Event]) -> set[str]:
    compacted: set[str] = set()
    for e in events:
        if isinstance(e, ToolOutputCompacted):
            tid = getattr(e, "tool_use_id", "")
            if isinstance(tid, str) and tid:
                compacted.add(tid)
    return compacted


def rebuild_messages(events: list[Event], *, max_events: int, max_bytes: int) -> list[Mapping[str, Any]]:
    events2 = _filter_to_latest_summary_pivot(_filter_to_head(events))
    compacted_ids = _collect_compacted_tool_ids(events2)

    messages_rev: list[Mapping[str, Any]] = []
    total_bytes = 0

    for e in reversed(events2):
        msg: Mapping[str, Any] | None = None
        if isinstance(e, UserMessage):
            msg = {"role": "user", "content": e.text}
        elif isinstance(e, UserCompaction):
            msg = {"role": "user", "content": COMPACTION_MARKER_QUESTION}
        elif isinstance(e, AssistantMessage):
            msg = {"role": "assistant", "content": e.text}
        elif isinstance(e, ToolUse):
            # Rebuild an assistant tool-call message so future provider calls that include tool results
            # remain valid for OpenAI-compatible gateways that require tool_call_id linkage.
            msg = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": e.tool_use_id,
                        "type": "function",
                        "function": {"name": e.name, "arguments": json.dumps(dict(e.input or {}), ensure_ascii=False)},
                    }
                ],
            }
        elif isinstance(e, ToolResult):
            content = (
                _TOOL_OUTPUT_PLACEHOLDER
                if e.tool_use_id in compacted_ids
                else json.dumps(_tool_result_content(e), ensure_ascii=False)
            )
            msg = {
                "role": "tool",
                "tool_call_id": e.tool_use_id,
                "content": content,
            }

        if msg is None:
            continue

        content = msg.get("content") or ""
        size = len(str(content).encode("utf-8"))
        if len(messages_rev) >= max_events:
            break
        if total_bytes + size > max_bytes:
            break

        total_bytes += size
        messages_rev.append(msg)

    messages = list(reversed(messages_rev))

    # Safety: drop any tool results that don't have a preceding tool_calls entry in the reconstructed messages.
    # Some providers reject histories with unmatched tool_call_id.
    seen_tool_call_ids: set[str] = set()
    filtered: list[Mapping[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant" and isinstance(m.get("tool_calls"), list):
            for tc in m.get("tool_calls") or []:
                if isinstance(tc, dict):
                    tc_id = tc.get("id")
                    if isinstance(tc_id, str) and tc_id:
                        seen_tool_call_ids.add(tc_id)
            filtered.append(m)
            continue
        if m.get("role") == "tool":
            tc_id = m.get("tool_call_id")
            if isinstance(tc_id, str) and tc_id and tc_id in seen_tool_call_ids:
                filtered.append(m)
            continue
        filtered.append(m)

    return filtered


def rebuild_responses_input(events: list[Event], *, max_events: int, max_bytes: int) -> list[Mapping[str, Any]]:
    events2 = _filter_to_latest_summary_pivot(_filter_to_head(events))
    compacted_ids = _collect_compacted_tool_ids(events2)

    items_rev: list[Mapping[str, Any]] = []
    total_bytes = 0

    for e in reversed(events2):
        item: Mapping[str, Any] | None = None
        if isinstance(e, UserMessage):
            item = {"role": "user", "content": e.text}
        elif isinstance(e, UserCompaction):
            item = {"role": "user", "content": COMPACTION_MARKER_QUESTION}
        elif isinstance(e, AssistantMessage):
            item = {"role": "assistant", "content": e.text}
        elif isinstance(e, ToolUse):
            item = {
                "type": "function_call",
                "call_id": e.tool_use_id,
                "name": e.name,
                "arguments": json.dumps(dict(e.input or {}), ensure_ascii=False),
            }
        elif isinstance(e, ToolResult):
            output = (
                _TOOL_OUTPUT_PLACEHOLDER
                if e.tool_use_id in compacted_ids
                else json.dumps(_tool_result_content(e), ensure_ascii=False)
            )
            item = {
                "type": "function_call_output",
                "call_id": e.tool_use_id,
                "output": output,
            }

        if item is None:
            continue

        content = item.get("content") or item.get("output") or ""
        size = len(str(content).encode("utf-8"))
        if len(items_rev) >= max_events:
            break
        if total_bytes + size > max_bytes:
            break

        total_bytes += size
        items_rev.append(item)

    items = list(reversed(items_rev))

    seen_call_ids: set[str] = set()
    filtered: list[Mapping[str, Any]] = []
    for it in items:
        if it.get("type") == "function_call":
            call_id = it.get("call_id")
            if isinstance(call_id, str) and call_id:
                seen_call_ids.add(call_id)
            filtered.append(it)
            continue
        if it.get("type") == "function_call_output":
            call_id = it.get("call_id")
            if isinstance(call_id, str) and call_id and call_id in seen_call_ids:
                filtered.append(it)
            continue
        filtered.append(it)

    return filtered
