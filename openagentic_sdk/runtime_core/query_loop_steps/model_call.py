from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping, Sequence

from ...events import AssistantDelta
from ...options import OpenAgenticOptions
from ...providers.base import ToolCall
from ...sessions.store import FileSessionStore

from .model_call_complete import complete_model_call
from .model_call_stream import iter_stream_model_call
from .types import ModelCallDone, ModelCallInterrupted


async def iter_model_call(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    provider_protocol: str,
    messages: list[Mapping[str, Any]],
    tool_schemas: Sequence[Mapping[str, Any]],
    store: FileSessionStore,
    session_id: str,
    supports_previous_response_id: bool,
    previous_response_id: str | None,
    pending_responses_tool_calls: list[ToolCall],
    pending_responses_history: list[Mapping[str, Any]],
) -> AsyncIterator[AssistantDelta | ModelCallDone | ModelCallInterrupted]:
    if hasattr(options.provider, "stream"):
        async for ev in iter_stream_model_call(
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
            yield ev
        return

    done = await complete_model_call(
        runtime,
        options=options,
        provider_protocol=provider_protocol,
        messages=messages,
        tool_schemas=tool_schemas,
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    )
    yield done

