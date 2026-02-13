from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...events import AssistantMessage
from ...options import OpenAgenticOptions
from ...providers.base import ModelOutput
from ...sessions.store import FileSessionStore

from .compaction_driver import iter_run_compaction_step
from .step_parts import StepPostDone
from .terminal import emit_end, emit_no_output
from .tool_driver import ToolStepDone, iter_run_tool_step
from .types import CompactionDone, StepState
from .utils import collect_events


async def iter_step_post(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    store: FileSessionStore,
    session_id: str,
    provider_protocol: str,
    model_out: ModelOutput,
    model_ctx: Mapping[str, Any],
    state: StepState,
    steps: int,
) -> AsyncIterator[Any | StepPostDone]:
    messages = list(state.messages)
    supports_previous_response_id = state.supports_previous_response_id
    previous_response_id = state.previous_response_id
    pending_responses_tool_calls = list(state.pending_responses_tool_calls)
    pending_responses_history = list(state.pending_responses_history)

    if model_out.tool_calls:
        tool_done: ToolStepDone | None = None
        async for ev in iter_run_tool_step(
            runtime,
            provider_protocol=provider_protocol,
            supports_previous_response_id=supports_previous_response_id,
            model_out=model_out,
            messages=messages,
            store=store,
            session_id=session_id,
            hooks=options.hooks,
            previous_response_id=previous_response_id,
            pending_responses_tool_calls=pending_responses_tool_calls,
            pending_responses_history=pending_responses_history,
        ):
            if isinstance(ev, ToolStepDone):
                tool_done = ev
                break
            yield ev
        assert tool_done is not None
        next_state = StepState(
            messages=list(tool_done.messages),
            supports_previous_response_id=tool_done.supports_previous_response_id,
            previous_response_id=tool_done.previous_response_id,
            pending_responses_tool_calls=list(tool_done.pending_responses_tool_calls),
            pending_responses_history=list(tool_done.pending_responses_history),
        )
        yield StepPostDone(state=next_state, should_continue=tool_done.should_continue)
        return

    if model_out.assistant_text is None:
        for ev in await collect_events(
            emit_no_output(
                runtime,
                options=options,
                store=store,
                session_id=session_id,
                context=model_ctx,
                steps=steps,
            )
        ):
            yield ev
        return

    msg = AssistantMessage(
        text=model_out.assistant_text,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, msg)
    yield msg

    compaction_done: CompactionDone | None = None
    async for ev in iter_run_compaction_step(
        runtime,
        options=options,
        store=store,
        session_id=session_id,
        provider_protocol=provider_protocol,
        supports_previous_response_id=supports_previous_response_id,
        model_out=model_out,
        messages=messages,
        previous_response_id=previous_response_id,
    ):
        if isinstance(ev, CompactionDone):
            compaction_done = ev
            break
        yield ev
    assert compaction_done is not None

    next_state = StepState(
        messages=list(compaction_done.messages),
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=compaction_done.previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    )
    if compaction_done.should_continue:
        yield StepPostDone(state=next_state, should_continue=True)
        return

    for ev in await collect_events(
        emit_end(
            runtime,
            options=options,
            store=store,
            session_id=session_id,
            context=model_ctx,
            model_out=model_out,
            provider_protocol=provider_protocol,
            supports_previous_response_id=supports_previous_response_id,
            previous_response_id=compaction_done.previous_response_id,
            steps=steps,
        )
    ):
        yield ev

