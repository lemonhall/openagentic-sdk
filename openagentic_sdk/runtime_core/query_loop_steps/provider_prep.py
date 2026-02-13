from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...options import OpenAgenticOptions

from .tool_schemas import build_tool_schemas, select_tool_names


def ensure_base_system_prompt(runtime: Any, messages: list[Mapping[str, Any]]) -> None:
    base_role = getattr(runtime, "_base_system_role", None) or "system"
    if getattr(runtime, "_base_system_prompt", None) and messages and messages[0].get("role") == base_role:
        messages[0] = {"role": base_role, "content": runtime._base_system_prompt}


async def prepare_provider_call(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    store: Any,
    session_id: str,
    provider_protocol: str,
    messages: list[Mapping[str, Any]],
    supports_previous_response_id: bool,
) -> tuple[Sequence[Mapping[str, Any]], list[Mapping[str, Any]], list[Any]]:
    tool_names = select_tool_names(options)
    tool_schemas: Sequence[Mapping[str, Any]] = build_tool_schemas(
        options=options,
        provider_protocol=provider_protocol,
        tool_names=tool_names,
    )

    prep_events: list[Any] = []
    if provider_protocol == "legacy" or not supports_previous_response_id:
        async for ev in runtime._maybe_prune_tool_outputs(store=store, session_id=session_id):
            prep_events.append(ev)
        messages = runtime._rebuild_provider_input(
            store=store,
            session_id=session_id,
            provider_protocol=provider_protocol,
            options=options,
        )

    ensure_base_system_prompt(runtime, messages)
    return tool_schemas, messages, prep_events

