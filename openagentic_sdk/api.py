from __future__ import annotations

from typing import Any, AsyncIterable, AsyncIterator

from .message_query import query_messages as _query_messages
from .options import OpenAgenticOptions
from .prompting import coerce_prompt
from .runtime import AgentRuntime, RunResult
from .session_tracking import capture_root_session_id


async def query(*, prompt: str | AsyncIterable[dict[str, Any]], options: OpenAgenticOptions) -> AsyncIterator[Any]:
    runtime = AgentRuntime(options)
    prompt_text = await coerce_prompt(prompt)
    async for e in runtime.query(prompt_text):
        yield e


async def query_messages(*, prompt: str | AsyncIterable[dict[str, Any]], options: OpenAgenticOptions):
    prompt_text = await coerce_prompt(prompt)
    async for m in _query_messages(prompt=prompt_text, options=options):
        yield m


async def run(*, prompt: str | AsyncIterable[dict[str, Any]], options: OpenAgenticOptions) -> RunResult:
    events: list[Any] = []
    final_text = ""
    session_id = options.resume or ""
    async for e in query(prompt=prompt, options=options):
        events.append(e)
        session_id = capture_root_session_id(session_id, e)
        if getattr(e, "type", None) == "result":
            final_text = getattr(e, "final_text", "")
    return RunResult(final_text=final_text, session_id=session_id, events=events)
