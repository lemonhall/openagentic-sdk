from __future__ import annotations

from typing import Any, Mapping

from ...events import Result
from ...options import OpenAgenticOptions
from ...providers.base import ToolCall
from ...sessions.rebuild import rebuild_messages, rebuild_responses_input
from ...sessions.store import FileSessionStore
from ...subagents.session_meta import build_authoritative_session_metadata
from ..common import _default_session_root
from .types import SessionBootstrap


def get_or_create_store(options: OpenAgenticOptions) -> FileSessionStore:
    store = options.session_store
    if store is not None:
        return store
    root = options.session_root or _default_session_root()
    return FileSessionStore(root_dir=root)


def bootstrap_session(options: OpenAgenticOptions, store: FileSessionStore) -> SessionBootstrap:
    previous_response_id: str | None = None
    supports_previous_response_id = True
    pending_responses_tool_calls: list[ToolCall] = []
    pending_responses_history: list[Mapping[str, Any]] = []
    resume_protocol: str | None = None

    if options.resume:
        session_id = options.resume
        past_events = store.read_events(session_id)

        for e in reversed(past_events):
            if isinstance(e, Result) and isinstance(getattr(e, "provider_metadata", None), dict):
                pm = e.provider_metadata or {}
                proto = pm.get("protocol")
                if isinstance(proto, str) and proto:
                    resume_protocol = proto
                spri = pm.get("supports_previous_response_id")
                if isinstance(spri, bool):
                    supports_previous_response_id = spri
                break

        for e in reversed(past_events):
            if isinstance(e, Result) and isinstance(getattr(e, "response_id", None), str) and e.response_id:
                previous_response_id = e.response_id
                break

        if resume_protocol == "responses" and supports_previous_response_id is False:
            messages = list(
                rebuild_responses_input(
                    past_events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        else:
            messages = list(
                rebuild_messages(
                    past_events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
    else:
        metadata: dict[str, Any] = build_authoritative_session_metadata(
            cwd=options.cwd,
            provider_name=getattr(options.provider, "name", "unknown"),
            model=options.model,
            setting_sources=options.setting_sources,
            allowed_tools=options.allowed_tools,
        )
        session_id = store.create_session(metadata=metadata)
        messages = []

    return SessionBootstrap(
        store=store,
        session_id=session_id,
        messages=messages,
        resume_protocol=resume_protocol,
        previous_response_id=previous_response_id,
        supports_previous_response_id=supports_previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    )
