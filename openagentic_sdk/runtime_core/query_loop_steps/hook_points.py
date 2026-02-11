from __future__ import annotations

from typing import Any, Mapping

from ...providers.base import ModelOutput

from .terminal import emit_blocked
from .utils import collect_events


async def run_before_model_call(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    model_ctx: Mapping[str, Any],
    messages: list[Mapping[str, Any]],
    steps: int,
) -> tuple[list[Mapping[str, Any]] | None, list[Any]]:
    messages2, hook_events, decision = await options.hooks.run_before_model_call(messages=messages, context=dict(model_ctx))
    out_events: list[Any] = []
    for he in hook_events:
        store.append_event(session_id, he)
        out_events.append(he)

    if decision is not None and decision.block:
        out_events.extend(
            await collect_events(
                emit_blocked(
                    runtime,
                    options=options,
                    store=store,
                    session_id=session_id,
                    context=model_ctx,
                    phase="before_model_call",
                    reason=decision.block_reason,
                    steps=steps,
                )
            )
        )
        return None, out_events

    return list(messages2), out_events


async def run_after_model_call(
    runtime: Any,
    *,
    options: Any,
    store: Any,
    session_id: str,
    model_ctx: Mapping[str, Any],
    model_out: ModelOutput,
    steps: int,
) -> tuple[ModelOutput | None, list[Any]]:
    model_out2, hook_events2, decision2 = await options.hooks.run_after_model_call(output=model_out, context=dict(model_ctx))
    out_events: list[Any] = []
    for he in hook_events2:
        store.append_event(session_id, he)
        out_events.append(he)

    if decision2 is not None and decision2.block:
        out_events.extend(
            await collect_events(
                emit_blocked(
                    runtime,
                    options=options,
                    store=store,
                    session_id=session_id,
                    context=model_ctx,
                    phase="after_model_call",
                    reason=decision2.block_reason,
                    steps=steps,
                )
            )
        )
        return None, out_events

    return model_out2, out_events

