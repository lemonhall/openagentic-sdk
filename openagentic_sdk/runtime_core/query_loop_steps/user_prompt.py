from __future__ import annotations

import uuid
from typing import Any

from ..common import _maybe_expand_execute_skill_prompt, _maybe_expand_list_skills_prompt
from ...events import Result, UserMessage
from ...options import OpenAgenticOptions
from ...sessions.store import FileSessionStore
from ...commands import load_command_template


async def run_user_prompt_submit(runtime: Any, *, options: OpenAgenticOptions, prompt: str, store: FileSessionStore, session_id: str):
    prompt2, hook_events0, decision0 = await options.hooks.run_user_prompt_submit(
        prompt=prompt,
        context={"session_id": session_id, "agent_name": runtime._agent_name},
    )
    for he in hook_events0:
        store.append_event(session_id, he)
        yield he

    if decision0 is not None and decision0.block:
        for he in await options.hooks.run_session_end(context={"session_id": session_id, "agent_name": runtime._agent_name}):
            store.append_event(session_id, he)
            yield he
        final = Result(
            final_text="",
            session_id=session_id,
            stop_reason=f"blocked:user_prompt_submit:{decision0.block_reason or 'blocked'}",
            steps=0,
            parent_tool_use_id=runtime._parent_tool_use_id,
            agent_name=runtime._agent_name,
        )
        store.append_event(session_id, final)
        yield final
        return

    prompt3 = _maybe_expand_execute_skill_prompt(prompt2, options)
    prompt3 = _maybe_expand_list_skills_prompt(prompt3, options)

    # OpenCode-style direct slash command execution: if the user typed
    # `/name ...` and the command exists, expand it before sending to the
    # model (no tool call required).
    if isinstance(prompt3, str) and prompt3.lstrip().startswith("/"):
        s = prompt3.lstrip()
        # Only consider the first line for command parsing; remaining
        # lines are preserved as part of the args.
        first, *rest = s.splitlines()
        first = first.strip()
        if first.startswith("/") and len(first) > 1:
            parts = first[1:].split(None, 1)
            cmd_name = parts[0].strip() if parts else ""
            cmd_args = (parts[1] if len(parts) > 1 else "")
            if rest:
                cmd_args = (cmd_args + "\n" + "\n".join(rest)).strip()

            if cmd_name:
                try:
                    project_dir = options.project_dir or options.cwd
                    if load_command_template(name=cmd_name, project_dir=str(project_dir)) is not None:
                        rendered, _, _ = await runtime._render_slash_command(
                            session_id=session_id,
                            tool_use_id=f"usercmd:{uuid.uuid4().hex}",
                            name=cmd_name,
                            args=cmd_args,
                        )
                        prompt3 = rendered
                except Exception:  # noqa: BLE001
                    # Fall back to raw prompt if expansion fails.
                    pass

    store.append_event(
        session_id,
        UserMessage(
            text=prompt3,
            parent_tool_use_id=runtime._parent_tool_use_id,
            agent_name=runtime._agent_name,
        ),
    )
    yield prompt3
