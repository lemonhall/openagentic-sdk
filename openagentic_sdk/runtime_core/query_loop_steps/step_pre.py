from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...options import OpenAgenticOptions
from ...providers.base import ModelOutput, ToolCall
from ...sessions.store import FileSessionStore

from .hook_points import run_after_model_call, run_before_model_call
from .model_driver import iter_model_call_with_interrupt_handling
from .provider_prep import prepare_provider_call
from .step_parts import StepPreDone
from .types import ModelCallDone, StepState


async def iter_step_pre(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    store: FileSessionStore,
    session_id: str,
    provider_protocol: str,
    messages: list[Mapping[str, Any]],
    supports_previous_response_id: bool,
    previous_response_id: str | None,
    pending_responses_tool_calls: list[ToolCall],
    pending_responses_history: list[Mapping[str, Any]],
    steps: int,
) -> AsyncIterator[Any | StepPreDone]:
    tool_schemas, messages, prep_events = await prepare_provider_call(
        runtime,
        options=options,
        store=store,
        session_id=session_id,
        provider_protocol=provider_protocol,
        messages=messages,
        supports_previous_response_id=supports_previous_response_id,
    )
    for ev in prep_events:
        yield ev

    model_ctx = {
        "session_id": session_id,
        "model": options.model,
        "provider_name": getattr(options.provider, "name", "unknown"),
        "agent_name": runtime._agent_name,
    }

    messages2, before_events = await run_before_model_call(
        runtime,
        options=options,
        store=store,
        session_id=session_id,
        model_ctx=model_ctx,
        messages=messages,
        steps=steps,
    )
    for ev in before_events:
        yield ev
    if messages2 is None:
        return
    messages = list(messages2)

    model_done: ModelCallDone | None = None
    async for ev in iter_model_call_with_interrupt_handling(
        runtime,
        options=options,
        provider_protocol=provider_protocol,
        messages=messages,
        tool_schemas=tool_schemas,
        store=store,
        session_id=session_id,
        model_ctx=model_ctx,
        steps=steps,
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    ):
        if isinstance(ev, ModelCallDone):
            model_done = ev
            break
        yield ev
    if model_done is None:
        return

    messages = list(model_done.messages)
    supports_previous_response_id = model_done.supports_previous_response_id
    model_out: ModelOutput = model_done.model_out

    model_out2, after_events = await run_after_model_call(
        runtime,
        options=options,
        store=store,
        session_id=session_id,
        model_ctx=model_ctx,
        model_out=model_out,
        steps=steps,
    )
    for ev in after_events:
        yield ev
    if model_out2 is None:
        return

    state = StepState(
        messages=list(messages),
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=list(pending_responses_tool_calls),
        pending_responses_history=list(pending_responses_history),
    )
    yield StepPreDone(state=state, model_out=model_out2, model_ctx=model_ctx)

