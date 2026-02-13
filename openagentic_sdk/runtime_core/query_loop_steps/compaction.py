from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...compaction import would_overflow
from ...events import UserCompaction, UserMessage
from ...options import OpenAgenticOptions
from ...providers.base import ModelOutput
from ...sessions.store import FileSessionStore

from .types import CompactionDone


async def iter_auto_compaction(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    store: FileSessionStore,
    session_id: str,
    provider_protocol: str,
    supports_previous_response_id: bool,
    model_out: ModelOutput,
    messages: list[Mapping[str, Any]],
    previous_response_id: str | None,
) -> AsyncIterator[Any | CompactionDone]:
    eligible = options.compaction.auto and (provider_protocol == "legacy" or not supports_previous_response_id)
    if not eligible:
        yield CompactionDone(messages=list(messages), previous_response_id=previous_response_id, should_continue=False)
        return

    usage = model_out.usage if isinstance(model_out.usage, dict) else None
    if not would_overflow(compaction=options.compaction, usage=usage):
        yield CompactionDone(messages=list(messages), previous_response_id=previous_response_id, should_continue=False)
        return

    marker = UserCompaction(
        auto=True,
        reason="overflow",
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    )
    store.append_event(session_id, marker)
    yield marker

    async for ev in runtime._run_compaction_pass(store=store, session_id=session_id, provider_protocol=provider_protocol):
        yield ev

    messages = runtime._rebuild_provider_input(
        store=store,
        session_id=session_id,
        provider_protocol=provider_protocol,
        options=options,
    )
    previous_response_id = None

    cont = "Continue if you have next steps"
    store.append_event(
        session_id,
        UserMessage(
            text=cont,
            parent_tool_use_id=runtime._parent_tool_use_id,
            agent_name=runtime._agent_name,
        ),
    )
    messages.append({"role": "user", "content": cont})

    yield CompactionDone(messages=list(messages), previous_response_id=previous_response_id, should_continue=True)

