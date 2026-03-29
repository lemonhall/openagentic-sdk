from __future__ import annotations

from typing import Any


def capture_root_session_id(current_session_id: str, event: Any) -> str:
    if getattr(event, "type", None) != "system.init":
        return current_session_id

    session_id = getattr(event, "session_id", None)
    if not isinstance(session_id, str) or not session_id:
        return current_session_id

    agent_name = getattr(event, "agent_name", None)
    if isinstance(agent_name, str) and agent_name:
        return current_session_id

    parent_tool_use_id = getattr(event, "parent_tool_use_id", None)
    if isinstance(parent_tool_use_id, str) and parent_tool_use_id:
        return current_session_id

    return session_id
