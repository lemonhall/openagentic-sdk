from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Mapping

from ..common import _tool_result_payload
from ...events import ToolResult
from ...providers.base import ModelOutput, ToolCall
from ...sessions.store import FileSessionStore

from .types import ToolPlumbingDone


async def iter_tool_plumbing(
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
) -> AsyncIterator[Any | ToolPlumbingDone]:
    tool_calls = list(model_out.tool_calls or [])
    pending_responses_tool_calls = tool_calls

    if provider_protocol == "legacy":
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.tool_use_id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            async for e in runtime._run_tool_call(session_id=session_id, tool_call=tc, store=store, hooks=hooks):
                yield e
                if isinstance(e, ToolResult):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.tool_use_id,
                            "content": json.dumps(_tool_result_payload(e), ensure_ascii=False),
                        }
                    )
        yield ToolPlumbingDone(
            messages=list(messages),
            should_continue=True,
            previous_response_id=previous_response_id,
            supports_previous_response_id=supports_previous_response_id,
            pending_responses_tool_calls=pending_responses_tool_calls,
            pending_responses_history=pending_responses_history,
        )
        return

    if supports_previous_response_id:
        tool_output_items: list[Mapping[str, Any]] = []
        for tc in tool_calls:
            async for e in runtime._run_tool_call(session_id=session_id, tool_call=tc, store=store, hooks=hooks):
                yield e
                if isinstance(e, ToolResult):
                    tool_output_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": tc.tool_use_id,
                            "output": json.dumps(_tool_result_payload(e), ensure_ascii=False),
                        }
                    )
        if model_out.response_id:
            previous_response_id = model_out.response_id
        pending_responses_history = list(messages)
        messages = list(tool_output_items)
        yield ToolPlumbingDone(
            messages=list(messages),
            should_continue=True,
            previous_response_id=previous_response_id,
            supports_previous_response_id=supports_previous_response_id,
            pending_responses_tool_calls=pending_responses_tool_calls,
            pending_responses_history=pending_responses_history,
        )
        return

    for tc in tool_calls:
        messages.append(
            {
                "type": "function_call",
                "call_id": tc.tool_use_id,
                "name": tc.name,
                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
            }
        )
        async for e in runtime._run_tool_call(session_id=session_id, tool_call=tc, store=store, hooks=hooks):
            yield e
            if isinstance(e, ToolResult):
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": tc.tool_use_id,
                        "output": json.dumps(_tool_result_payload(e), ensure_ascii=False),
                    }
                )

    yield ToolPlumbingDone(
        messages=list(messages),
        should_continue=True,
        previous_response_id=previous_response_id,
        supports_previous_response_id=supports_previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    )

