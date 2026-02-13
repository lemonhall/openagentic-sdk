from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..._version import __version__ as _SDK_VERSION
from ...events import SystemInit
from ...options import OpenAgenticOptions
from ...sessions.store import FileSessionStore


async def emit_system_init_and_session_start(
    *,
    options: OpenAgenticOptions,
    store: FileSessionStore,
    session_id: str,
    parent_tool_use_id: str | None,
    agent_name: str | None,
) -> AsyncIterator[Any]:
    init = SystemInit(
        session_id=session_id,
        cwd=options.cwd,
        sdk_version=_SDK_VERSION,
        parent_tool_use_id=parent_tool_use_id,
        agent_name=agent_name,
        enabled_tools=options.tools.names(),
        enabled_providers=[getattr(options.provider, "name", "unknown")],
    )
    store.append_event(session_id, init)
    yield init

    for he in await options.hooks.run_session_start(context={"session_id": session_id, "agent_name": agent_name}):
        store.append_event(session_id, he)
        yield he

