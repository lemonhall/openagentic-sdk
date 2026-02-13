from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..common import (
    _extract_function_call_outputs,
    _filter_supported_kwargs,
    _looks_like_outputs_without_calls,
    _no_tool_call_found_for_call_output_error,
    _prepend_function_calls_for_responses,
    _unsupported_previous_response_id_error,
)
from ...options import OpenAgenticOptions
from ...providers.base import ToolCall

from .types import ModelCallDone


async def complete_model_call(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    provider_protocol: str,
    messages: list[Mapping[str, Any]],
    tool_schemas: Sequence[Mapping[str, Any]],
    supports_previous_response_id: bool,
    previous_response_id: str | None,
    pending_responses_tool_calls: list[ToolCall],
    pending_responses_history: list[Mapping[str, Any]],
) -> ModelCallDone:
    complete_fn: Any = getattr(options.provider, "complete")

    if provider_protocol == "legacy":
        kwargs = {"model": options.model, "messages": messages, "tools": tool_schemas, "api_key": options.api_key}
        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
        return ModelCallDone(model_out=model_out, messages=list(messages), supports_previous_response_id=supports_previous_response_id)

    prev_id = previous_response_id if supports_previous_response_id else None
    instructions = getattr(runtime, "_base_instructions", None)
    try:
        kwargs = {
            "model": options.model,
            "input": messages,
            "tools": tool_schemas,
            "api_key": options.api_key,
            "previous_response_id": prev_id,
            "store": True,
            "instructions": instructions,
        }
        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
    except RuntimeError as e:
        can_retry_prev = supports_previous_response_id and previous_response_id is not None and _unsupported_previous_response_id_error(e)
        can_retry_link = supports_previous_response_id and _no_tool_call_found_for_call_output_error(e)
        can_retry = can_retry_prev or can_retry_link
        if not can_retry:
            raise
        supports_previous_response_id = False
        if pending_responses_tool_calls and pending_responses_history and _looks_like_outputs_without_calls(messages):
            outs = _extract_function_call_outputs(messages)
            messages = [
                *list(pending_responses_history),
                *_prepend_function_calls_for_responses(pending_responses_tool_calls, outs),
            ]
        kwargs = {
            "model": options.model,
            "input": messages,
            "tools": tool_schemas,
            "api_key": options.api_key,
            "previous_response_id": None,
            "store": True,
            "instructions": instructions,
        }
        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))

    return ModelCallDone(model_out=model_out, messages=list(messages), supports_previous_response_id=supports_previous_response_id)

