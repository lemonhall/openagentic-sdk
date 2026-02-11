from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .events import AssistantMessage, Event, ToolOutputCompacted, ToolResult, ToolUse, UserCompaction, UserMessage
from .options import CompactionOptions


COMPACTION_SYSTEM_PROMPT = """You are a helpful AI assistant tasked with summarizing conversations.

When asked to summarize, provide a detailed but concise summary of the conversation.
Focus on information that would be helpful for continuing the conversation, including:
- What was done
- What is currently being worked on
- Which files are being modified
- What needs to be done next
- Key user requests, constraints, or preferences that should persist
- Important technical decisions and why they were made

Your summary should be comprehensive enough to provide context but concise enough to be quickly understood.
""".strip()


COMPACTION_MARKER_QUESTION = "What did we do so far?"


COMPACTION_USER_INSTRUCTION = (
    "Provide a detailed prompt for continuing our conversation above. Focus on information that would be helpful for "
    "continuing the conversation, including what we did, what we're doing, which files we're working on, and what we're "
    "going to do next considering new session will not have access to our conversation."
)


TOOL_OUTPUT_PLACEHOLDER = "[Old tool result content cleared]"


@dataclass(frozen=True, slots=True)
class UsageTotals:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int


def _int(v: Any) -> int:
    try:
        return int(v)
    except Exception:  # noqa: BLE001
        return 0


def parse_usage_totals(usage: Mapping[str, Any] | None) -> UsageTotals | None:
    if not isinstance(usage, dict) or not usage:
        return None

    input_tokens = _int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    output_tokens = _int(usage.get("output_tokens") or usage.get("completion_tokens"))
    cache_read_tokens = _int(usage.get("cache_read_tokens") or usage.get("cached_tokens"))
    cache_write_tokens = _int(usage.get("cache_write_tokens"))
    total_tokens = _int(usage.get("total_tokens"))

    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens

    if total_tokens <= 0:
        return None

    return UsageTotals(
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        cache_read_tokens=max(0, cache_read_tokens),
        cache_write_tokens=max(0, cache_write_tokens),
        total_tokens=max(0, total_tokens),
    )


def would_overflow(*, compaction: CompactionOptions, usage: Mapping[str, Any] | None) -> bool:
    totals = parse_usage_totals(usage)
    if totals is None:
        return False

    context_limit = int(compaction.context_limit or 0)
    if context_limit <= 0:
        return False

    output_cap = max(0, int(compaction.global_output_cap or 0))
    output_limit = compaction.output_limit
    max_output_tokens = min(int(output_limit), output_cap) if isinstance(output_limit, int) and output_limit > 0 else output_cap

    reserved = compaction.reserved
    if not isinstance(reserved, int) or reserved <= 0:
        reserved = min(20_000, max_output_tokens)

    effective_limit = compaction.input_limit if isinstance(compaction.input_limit, int) and compaction.input_limit > 0 else context_limit
    usable = int(effective_limit) - max(0, int(reserved))
    if usable <= 0:
        return True

    # OpenCode parity: overflow is triggered at the boundary (>=).
    return totals.total_tokens >= usable


def estimate_tokens(text: str) -> int:
    # Lightweight heuristic (portable): tokens ~= chars/4.
    if not text:
        return 0
    return max(1, len(text) // 4)


def _safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(obj)


def _filter_to_latest_summary_pivot(events: list[Event]) -> list[Event]:
    last_summary_idx: int | None = None
    for i, e in enumerate(events):
        if isinstance(e, AssistantMessage) and bool(getattr(e, "is_summary", False)):
            last_summary_idx = i
    if last_summary_idx is None:
        return events
    return events[last_summary_idx:]


def select_tool_outputs_to_prune(*, events: list[Event], compaction: CompactionOptions) -> list[str]:
    """Return tool_use_ids to compact (append-only via ToolOutputCompacted events).

    This implements the portable pruning strategy described in COMPACTION.md.
    """

    if not compaction.prune:
        return []

    events2 = _filter_to_latest_summary_pivot(events)

    compacted_ids: set[str] = set()
    tool_name_by_id: dict[str, str] = {}
    for e in events2:
        if isinstance(e, ToolOutputCompacted):
            tid = getattr(e, "tool_use_id", "")
            if isinstance(tid, str) and tid:
                compacted_ids.add(tid)
        if isinstance(e, ToolUse):
            tid2 = getattr(e, "tool_use_id", "")
            nm = getattr(e, "name", "")
            if isinstance(tid2, str) and tid2 and isinstance(nm, str) and nm:
                tool_name_by_id[tid2] = nm

    protect = max(0, int(compaction.protect_tool_output_tokens or 0))
    min_prune = max(0, int(compaction.min_prune_tokens or 0))

    total = 0
    pruned_tokens = 0
    to_prune: list[tuple[str, int]] = []
    turns = 0

    # OpenCode: skip pruning until >=2 user turns are present.
    for e in reversed(events2):
        if isinstance(e, (UserMessage, UserCompaction)):
            turns += 1
            continue
        if turns < 2:
            continue
        if isinstance(e, AssistantMessage) and bool(getattr(e, "is_summary", False)):
            break
        if not isinstance(e, ToolResult):
            continue
        tid = e.tool_use_id
        if not isinstance(tid, str) or not tid:
            continue

        # Idempotence boundary: once we hit an already-compacted tool result,
        # stop scanning older results to avoid churn.
        if tid in compacted_ids:
            break

        tool_name = tool_name_by_id.get(tid, "")
        if isinstance(tool_name, str) and tool_name.lower() == "skill":
            continue

        cost = estimate_tokens(_safe_json_dumps(e.output))
        total += cost
        if total > protect:
            pruned_tokens += cost
            to_prune.append((tid, cost))

    # OpenCode: only apply if prunedTokens > PRUNE_MINIMUM (strict).
    if pruned_tokens <= min_prune:
        return []
    return [tid for tid, _ in to_prune]
