from __future__ import annotations

from typing import Any, AsyncIterator, Mapping

from ..events import (
    Result,
    ToolResult,
)
from ..options import OpenAgenticOptions
from ..providers.base import ToolCall
from ..sessions.store import FileSessionStore
from ..subagents.remote_dispatch import resolve_git_revision
from ..subagents.remote_types import RemoteTaskRequest


class TaskToolMixin:
    async def _handle_task_tool(
        self,
        *,
        session_id: str,
        tool_call: ToolCall,
        tool_input: Mapping[str, Any],
        store: FileSessionStore,
    ) -> AsyncIterator[Any]:
        options = self._options

        agent = tool_input.get("agent")
        task_prompt = tool_input.get("prompt")
        if not isinstance(agent, str) or not agent:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="InvalidTaskInput",
                error_message="Task: 'agent' must be a non-empty string",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return
        if not isinstance(task_prompt, str) or not task_prompt:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="InvalidTaskInput",
                error_message="Task: 'prompt' must be a non-empty string",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        definition = options.agents.get(agent)
        if definition is None:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="UnknownAgent",
                error_message=f"Unknown agent '{agent}'",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        if definition.executor.kind == "k3s":
            dispatcher = options.remote_task_dispatcher
            if dispatcher is None:
                result = ToolResult(
                    tool_use_id=tool_call.tool_use_id,
                    output=None,
                    is_error=True,
                    error_type="RemoteDispatcherUnavailable",
                    error_message=f"Agent '{agent}' requires remote task dispatch, but no dispatcher is configured",
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )
                store.append_event(session_id, result)
                yield result
                return

            try:
                git_revision = resolve_git_revision(cwd=options.cwd)
                request = RemoteTaskRequest(
                    parent_session_id=session_id,
                    parent_tool_use_id=tool_call.tool_use_id,
                    agent_name=agent,
                    prompt=task_prompt,
                    definition=definition,
                    cwd=options.cwd,
                    project_dir=options.project_dir,
                    git_revision=git_revision,
                )
                handle = await dispatcher.dispatch(request)
                child_final_text = ""
                async for child_event in handle.events:
                    store.append_event(session_id, child_event)
                    yield child_event
                    if isinstance(child_event, Result):
                        child_final_text = child_event.final_text

                result = ToolResult(
                    tool_use_id=tool_call.tool_use_id,
                    output={
                        "child_session_id": handle.child_session_id,
                        "final_text": child_final_text,
                        "dispatch_mode": "k3s",
                        "target_node": handle.target_node,
                        "git_revision": handle.git_revision,
                    },
                    is_error=False,
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )
            except Exception as e:  # noqa: BLE001
                result = ToolResult(
                    tool_use_id=tool_call.tool_use_id,
                    output=None,
                    is_error=True,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )
            store.append_event(session_id, result)
            yield result
            return

        child_session_id = store.create_session(
            metadata={
                "parent_session_id": session_id,
                "parent_tool_use_id": tool_call.tool_use_id,
                "agent_name": agent,
            }
        )
        child_options = OpenAgenticOptions(
            provider=definition.provider or options.provider,
            model=definition.model or options.model,
            api_key=options.api_key,
            cwd=options.cwd,
            max_steps=options.max_steps,
            timeout_s=options.timeout_s,
            tools=options.tools,
            allowed_tools=list(definition.tools) if definition.tools else options.allowed_tools,
            permission_gate=options.permission_gate,
            hooks=options.hooks,
            session_store=store,
            resume=child_session_id,
            setting_sources=options.setting_sources,
            agents=options.agents,
        )

        # AgentRuntime lived in the same module pre-refactor; import lazily to
        # avoid circular imports during module initialization.
        from .agent_runtime import AgentRuntime

        child_runtime = AgentRuntime(child_options, agent_name=agent, parent_tool_use_id=tool_call.tool_use_id)
        combined_prompt = definition.prompt + "\n\n" + task_prompt
        child_final_text = ""
        async for child_event in child_runtime.query(combined_prompt):
            store.append_event(session_id, child_event)
            yield child_event
            if isinstance(child_event, Result):
                child_final_text = child_event.final_text

        result = ToolResult(
            tool_use_id=tool_call.tool_use_id,
            output={"child_session_id": child_session_id, "final_text": child_final_text},
            is_error=False,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, result)
        yield result


