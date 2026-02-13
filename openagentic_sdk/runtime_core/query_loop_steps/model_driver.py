from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping, Sequence

from ...events import AssistantDelta
from ...options import OpenAgenticOptions
from ...providers.base import ToolCall
from ...sessions.store import FileSessionStore

from .model_call import iter_model_call
from .terminal import emit_interrupted
from .types import ModelCallDone, ModelCallInterrupted
from .utils import collect_events


async def iter_model_call_with_interrupt_handling(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    provider_protocol: str,
    messages: list[Mapping[str, Any]],
    tool_schemas: Sequence[Mapping[str, Any]],
    store: FileSessionStore,
    session_id: str,
    model_ctx: Mapping[str, Any],
    steps: int,
    supports_previous_response_id: bool,
    previous_response_id: str | None,
    pending_responses_tool_calls: list[ToolCall],
    pending_responses_history: list[Mapping[str, Any]],
) -> AsyncIterator[AssistantDelta | ModelCallDone | Any]:
    async for ev in iter_model_call(
        runtime,
        options=options,
        provider_protocol=provider_protocol,
        messages=messages,
        tool_schemas=tool_schemas,
        store=store,
        session_id=session_id,
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    ):
        if isinstance(ev, ModelCallInterrupted):
            for e2 in await collect_events(
                emit_interrupted(
                    runtime,
                    options=options,
                    store=store,
                    session_id=session_id,
                    context=model_ctx,
                    steps=steps,
                )
            ):
                yield e2
            return
        yield ev
        if isinstance(ev, ModelCallDone):
            return

