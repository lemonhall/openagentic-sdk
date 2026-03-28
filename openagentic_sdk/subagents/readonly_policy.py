from __future__ import annotations

from collections.abc import Sequence

from ..options import AgentDefinition

_REMOTE_SAFE_DEFAULT_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep", "WebFetch")
_REMOTE_BLOCKED_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"})


def build_remote_allowed_tools(
    definition: AgentDefinition,
    *,
    fallback_allowed_tools: Sequence[str] | None = None,
) -> tuple[str, ...]:
    configured = tuple(definition.tools) if definition.tools else tuple(fallback_allowed_tools or _REMOTE_SAFE_DEFAULT_TOOLS)
    return tuple(tool_name for tool_name in configured if tool_name not in _REMOTE_BLOCKED_TOOLS)
