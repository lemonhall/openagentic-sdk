from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Mapping

from ...providers.base import ModelOutput, ToolCall
from ...sessions.store import FileSessionStore

from .tool_plumbing import iter_tool_plumbing
from .types import ToolPlumbingDone


@dataclass(frozen=True, slots=True)
class ToolStepDone:
    messages: list[Mapping[str, Any]]
    previous_response_id: str | None
    supports_previous_response_id: bool
    pending_responses_tool_calls: list[ToolCall]
    pending_responses_history: list[Mapping[str, Any]]
    should_continue: bool


async def iter_run_tool_step(
    runtime: Any,
    *,
    provider_protocol: str,
    supports_previous_response_id: bool,
    model_out: ModelOutput,
    messages: list[Mapping[str, Any]],
    store: FileSessionStore,
    session_id: str,
    hooks: Any,
    previous_response_id: str | None,
    pending_responses_tool_calls: list[ToolCall],
    pending_responses_history: list[Mapping[str, Any]],
) -> AsyncIterator[Any | ToolStepDone]:
    done: ToolPlumbingDone | None = None
    async for ev in iter_tool_plumbing(
        runtime,
        provider_protocol=provider_protocol,
        supports_previous_response_id=supports_previous_response_id,
        model_out=model_out,
        messages=messages,
        store=store,
        session_id=session_id,
        hooks=hooks,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    ):
        if isinstance(ev, ToolPlumbingDone):
            done = ev
            break
        yield ev

    assert done is not None
    yield ToolStepDone(
        messages=list(done.messages),
        previous_response_id=done.previous_response_id,
        supports_previous_response_id=done.supports_previous_response_id,
        pending_responses_tool_calls=list(done.pending_responses_tool_calls),
        pending_responses_history=list(done.pending_responses_history),
        should_continue=done.should_continue,
    )

