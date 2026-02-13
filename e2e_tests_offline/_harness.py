from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.options import AgentDefinition, OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.sessions.store import FileSessionStore


def make_options_offline(
    root: Path,
    *,
    provider: Any,
    model: str = "offline-model",
    allowed_tools: Sequence[str] | None,
    include_partial_messages: bool = False,
    hooks: HookEngine | None = None,
    mcp_servers: Mapping[str, Any] | None = None,
    agents: Mapping[str, AgentDefinition] | None = None,
) -> OpenAgenticOptions:
    store = FileSessionStore(root_dir=root)
    opts = OpenAgenticOptions(
        provider=provider,
        model=model,
        api_key="offline",
        cwd=str(root),
        project_dir=str(root),
        session_store=store,
        permission_gate=PermissionGate(permission_mode="bypass"),
        allowed_tools=list(allowed_tools) if allowed_tools is not None else None,
        include_partial_messages=include_partial_messages,
        hooks=hooks or HookEngine(),
        mcp_servers=dict(mcp_servers) if mcp_servers is not None else None,
        agents=dict(agents) if agents is not None else {},
    )
    return replace(opts, max_steps=15)

