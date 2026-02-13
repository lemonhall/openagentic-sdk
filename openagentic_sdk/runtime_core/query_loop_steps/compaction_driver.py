from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Mapping

from ...options import OpenAgenticOptions
from ...providers.base import ModelOutput
from ...sessions.store import FileSessionStore

from .compaction import iter_auto_compaction
from .types import CompactionDone


async def iter_run_compaction_step(
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
    done: CompactionDone | None = None
    async for ev in iter_auto_compaction(
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
            done = ev
            break
        yield ev
    assert done is not None
    yield done

