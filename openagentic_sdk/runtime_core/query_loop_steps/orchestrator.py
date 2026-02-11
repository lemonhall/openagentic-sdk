from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..common import _detect_provider_protocol
from ...events import Result
from ...tools.task import TaskTool

from .session import bootstrap_session, get_or_create_store
from .session_events import emit_system_init_and_session_start
from .step_loop import run_step_loop
from .system_prompt import inject_project_system_prompt
from .user_prompt import run_user_prompt_submit


async def run_query(runtime: Any, prompt: str) -> AsyncIterator[Any]:
    options = runtime._options

    # Expose Task only when agents are configured.
    if options.agents:
        try:
            options.tools.get("Task")
        except KeyError:
            options.tools.register(TaskTool())

    store = get_or_create_store(options)
    boot = bootstrap_session(options, store)

    store = boot.store
    session_id = boot.session_id
    messages = list(boot.messages)
    previous_response_id = boot.previous_response_id
    supports_previous_response_id = boot.supports_previous_response_id
    pending_responses_tool_calls = list(boot.pending_responses_tool_calls)
    pending_responses_history = list(boot.pending_responses_history)

    async for ev in emit_system_init_and_session_start(
        options=options,
        store=store,
        session_id=session_id,
        parent_tool_use_id=runtime._parent_tool_use_id,
        agent_name=runtime._agent_name,
    ):
        yield ev

    provider_protocol: str = boot.resume_protocol or _detect_provider_protocol(options.provider)
    inject_project_system_prompt(runtime, options=options, provider_protocol=provider_protocol, messages=messages)

    prompt3: str | None = None
    async for ev in run_user_prompt_submit(runtime, options=options, prompt=prompt, store=store, session_id=session_id):
        if isinstance(ev, str):
            prompt3 = ev
            continue
        yield ev
        if isinstance(ev, Result):
            return
    assert prompt3 is not None
    messages.append({"role": "user", "content": prompt3})

    async for ev in run_step_loop(
        runtime,
        options=options,
        store=store,
        session_id=session_id,
        provider_protocol=provider_protocol,
        messages=messages,
        supports_previous_response_id=supports_previous_response_id,
        previous_response_id=previous_response_id,
        pending_responses_tool_calls=pending_responses_tool_calls,
        pending_responses_history=pending_responses_history,
    ):
        yield ev

