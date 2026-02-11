from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...events import Result
from ...options import OpenAgenticOptions
from ...sessions.store import FileSessionStore


async def emit_session_end(
    *,
    options: OpenAgenticOptions,
    store: FileSessionStore,
    session_id: str,
    context: Mapping[str, Any],
) -> AsyncIterator[Any]:
    for he in await options.hooks.run_session_end(context=dict(context)):
        store.append_event(session_id, he)
        yield he


async def emit_stop_and_session_end(
    *,
    options: OpenAgenticOptions,
    store: FileSessionStore,
    session_id: str,
    final_text: str,
    context: Mapping[str, Any],
) -> AsyncIterator[Any]:
    for he in await options.hooks.run_stop(final_text=final_text, context=dict(context)):
        store.append_event(session_id, he)
        yield he
    async for he in emit_session_end(options=options, store=store, session_id=session_id, context=context):
        yield he


def make_result(
    *,
    final_text: str,
    session_id: str,
    stop_reason: str,
    steps: int,
    parent_tool_use_id: str | None,
    agent_name: str | None,
    usage: Mapping[str, Any] | None = None,
    response_id: str | None = None,
    provider_metadata: Mapping[str, Any] | None = None,
) -> Result:
    return Result(
        final_text=final_text,
        session_id=session_id,
        stop_reason=stop_reason,
        usage=usage,
        response_id=response_id,
        provider_metadata=dict(provider_metadata) if provider_metadata else None,
        steps=steps,
        parent_tool_use_id=parent_tool_use_id,
        agent_name=agent_name,
    )

