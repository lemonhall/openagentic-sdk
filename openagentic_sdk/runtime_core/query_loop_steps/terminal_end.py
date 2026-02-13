from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...providers.base import ModelOutput

from .finalize import emit_stop_and_session_end, make_result


async def emit_end(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    context: Mapping[str, Any],
    model_out: ModelOutput,
    provider_protocol: str,
    supports_previous_response_id: bool,
    previous_response_id: str | None,
    steps: int,
) -> AsyncIterator[Any]:
    assert model_out.assistant_text is not None
    async for he in emit_stop_and_session_end(
        options=options,
        store=store,
        session_id=session_id,
        final_text=model_out.assistant_text,
        context=context,
    ):
        yield he

    final = make_result(
        final_text=model_out.assistant_text,
        session_id=session_id,
        stop_reason="end",
        usage=model_out.usage if isinstance(model_out.usage, dict) else None,
        response_id=model_out.response_id or previous_response_id,
        provider_metadata={
            **({"protocol": provider_protocol} if provider_protocol else {}),
            **(
                {"supports_previous_response_id": supports_previous_response_id}
                if provider_protocol == "responses"
                else {}
            ),
            **(dict(model_out.provider_metadata) if isinstance(model_out.provider_metadata, dict) else {}),
        }
        or None,
        steps=steps,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, final)
    yield final

