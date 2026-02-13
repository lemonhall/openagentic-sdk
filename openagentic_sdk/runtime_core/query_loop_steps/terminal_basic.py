from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from .finalize import emit_session_end, make_result


async def emit_interrupted(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    context: Mapping[str, Any],
    steps: int,
) -> AsyncIterator[Any]:
    async for he in emit_session_end(options=options, store=store, session_id=session_id, context=context):
        yield he
    final = make_result(
        final_text="",
        session_id=session_id,
        stop_reason="interrupted",
        steps=steps,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, final)
    yield final


async def emit_blocked(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    context: Mapping[str, Any],
    phase: str,
    reason: str | None,
    steps: int,
) -> AsyncIterator[Any]:
    async for he in emit_session_end(options=options, store=store, session_id=session_id, context=context):
        yield he
    final = make_result(
        final_text="",
        session_id=session_id,
        stop_reason=f"blocked:{phase}:{reason or 'blocked'}",
        steps=steps,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, final)
    yield final


async def emit_no_output(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    context: Mapping[str, Any],
    steps: int,
) -> AsyncIterator[Any]:
    async for he in emit_session_end(options=options, store=store, session_id=session_id, context=context):
        yield he
    final = make_result(
        final_text="",
        session_id=session_id,
        stop_reason="no_output",
        steps=steps,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, final)
    yield final


async def emit_max_steps(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    steps: int,
) -> AsyncIterator[Any]:
    end_ctx = {"session_id": session_id, "agent_name": runtime._agent_name}
    async for he in emit_session_end(options=options, store=store, session_id=session_id, context=end_ctx):
        yield he
    final = make_result(
        final_text="",
        session_id=session_id,
        stop_reason="max_steps",
        steps=steps,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, final)
    yield final

