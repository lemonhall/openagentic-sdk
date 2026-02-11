from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping, Sequence

from ..common import (
    _callable_accepts_kw,
    _extract_function_call_outputs,
    _filter_supported_kwargs,
    _looks_like_outputs_without_calls,
    _no_tool_call_found_for_call_output_error,
    _prepend_function_calls_for_responses,
    _unsupported_previous_response_id_error,
)
from ...events import AssistantDelta
from ...options import OpenAgenticOptions
from ...providers.base import ModelOutput, ToolCall
from ...sessions.store import FileSessionStore

from .types import ModelCallDone, ModelCallInterrupted


async def iter_stream_model_call(
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
    stream_fn: Any = getattr(options.provider, "stream")
    interrupted = False
    parts: list[str] = []
    tool_calls: list[ToolCall] = []
    stream_response_id: str | None = None
    stream_usage: Mapping[str, Any] | None = None

    for attempt in range(2):
        parts = []
        tool_calls = []
        stream_response_id = None
        stream_usage = None

        if provider_protocol == "legacy":
            kwargs = {"model": options.model, "messages": messages, "tools": tool_schemas, "api_key": options.api_key}
            stream_iter = stream_fn(**_filter_supported_kwargs(stream_fn, kwargs))
        else:
            can_thread = supports_previous_response_id and _callable_accepts_kw(stream_fn, "previous_response_id")
            prev_id = previous_response_id if can_thread else None
            instructions = getattr(runtime, "_base_instructions", None)
            kwargs = {
                "model": options.model,
                "input": messages,
                "tools": tool_schemas,
                "api_key": options.api_key,
                "previous_response_id": prev_id,
                "store": True,
                "instructions": instructions,
            }
            stream_iter = stream_fn(**_filter_supported_kwargs(stream_fn, kwargs))

        try:
            async for ev in stream_iter:
                if options.abort_event is not None and getattr(options.abort_event, "is_set", lambda: False)():
                    interrupted = True
                    break
                ev_type = getattr(ev, "type", None)
                if ev_type is None and isinstance(ev, dict):
                    ev_type = ev.get("type")
                if ev_type == "text_delta":
                    delta = getattr(ev, "delta", None)
                    if delta is None and isinstance(ev, dict):
                        delta = ev.get("delta")
                    if isinstance(delta, str) and delta:
                        parts.append(delta)
                        de = AssistantDelta(
                            text_delta=delta,
                            parent_tool_use_id=runtime._parent_tool_use_id,
                            agent_name=runtime._agent_name,
                        )
                        store.append_event(session_id, de)
                        yield de
                elif ev_type == "tool_call":
                    tc = getattr(ev, "tool_call", None)
                    if tc is None and isinstance(ev, dict):
                        tc = ev.get("tool_call")
                    if isinstance(tc, ToolCall):
                        tool_calls.append(tc)
                elif ev_type == "done":
                    rid = getattr(ev, "response_id", None)
                    if rid is None and isinstance(ev, dict):
                        rid = ev.get("response_id")
                    if isinstance(rid, str) and rid:
                        stream_response_id = rid
                    u = getattr(ev, "usage", None)
                    if u is None and isinstance(ev, dict):
                        u = ev.get("usage")
                    if isinstance(u, dict):
                        stream_usage = u
                    break
        except RuntimeError as e:
            can_retry_prev = (
                supports_previous_response_id and previous_response_id is not None and _unsupported_previous_response_id_error(e)
            )
            can_retry_link = supports_previous_response_id and _no_tool_call_found_for_call_output_error(e)
            can_retry = (
                provider_protocol != "legacy"
                and attempt == 0
                and supports_previous_response_id
                and not parts
                and not tool_calls
                and stream_response_id is None
                and (can_retry_prev or can_retry_link)
            )
            if can_retry:
                supports_previous_response_id = False
                if pending_responses_tool_calls and pending_responses_history and _looks_like_outputs_without_calls(messages):
                    outs = _extract_function_call_outputs(messages)
                    messages = [
                        *list(pending_responses_history),
                        *_prepend_function_calls_for_responses(pending_responses_tool_calls, outs),
                    ]
                continue
            raise
        break

    if interrupted:
        yield ModelCallInterrupted()
        return

    assistant_text = "".join(parts) if parts else None
    model_out = ModelOutput(
        assistant_text=assistant_text,
        tool_calls=tool_calls,
        usage=stream_usage,
        response_id=stream_response_id,
    )
    yield ModelCallDone(model_out=model_out, messages=list(messages), supports_previous_response_id=supports_previous_response_id)

