from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...options import OpenAgenticOptions
from ...providers.base import ToolCall
from ...sessions.store import FileSessionStore

from .step_parts import StepPostDone, StepPreDone
from .step_post import iter_step_post
from .step_pre import iter_step_pre
from .terminal import emit_interrupted, emit_max_steps
from .types import StepState
from .utils import collect_events


async def run_step_loop(
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
) -> AsyncIterator[Any]:
    # provider_protocol is computed before first system prompt injection.
    steps = 0
    state = StepState(
        messages=list(messages),
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=list(pending_responses_tool_calls),
        pending_responses_history=list(pending_responses_history),
    )

    while steps < options.max_steps:
        if options.abort_event is not None and getattr(options.abort_event, "is_set", lambda: False)():
            end_ctx = {"session_id": session_id, "agent_name": runtime._agent_name}
            for ev in await collect_events(
                emit_interrupted(runtime, options=options, store=store, session_id=session_id, context=end_ctx, steps=steps)
            ):
                yield ev
            return

        steps += 1

        pre_done: StepPreDone | None = None
        async for ev in iter_step_pre(
            runtime,
            options=options,
            store=store,
            session_id=session_id,
            provider_protocol=provider_protocol,
            messages=list(state.messages),
            supports_previous_response_id=state.supports_previous_response_id,
            previous_response_id=state.previous_response_id,
            pending_responses_tool_calls=list(state.pending_responses_tool_calls),
            pending_responses_history=list(state.pending_responses_history),
            steps=steps,
        ):
            if isinstance(ev, StepPreDone):
                pre_done = ev
                break
            yield ev
        if pre_done is None:
            return

        post_done: StepPostDone | None = None
        async for ev in iter_step_post(
            runtime,
            options=options,
            store=store,
            session_id=session_id,
            provider_protocol=provider_protocol,
            model_out=pre_done.model_out,
            model_ctx=pre_done.model_ctx,
            state=pre_done.state,
            steps=steps,
        ):
            if isinstance(ev, StepPostDone):
                post_done = ev
                break
            yield ev
        if post_done is None:
            return

        state = post_done.state
        if post_done.should_continue:
            continue
        return

    for ev in await collect_events(emit_max_steps(runtime, options=options, store=store, session_id=session_id, steps=steps)):
        yield ev

