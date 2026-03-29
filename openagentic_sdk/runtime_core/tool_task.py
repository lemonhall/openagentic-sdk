from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Mapping

from ..events import (
    Result,
    ToolResult,
)
from ..options import OpenAgenticOptions
from ..providers.base import ToolCall
from ..serialization import event_from_dict
from ..sessions.store import FileSessionStore
from ..subagents.actor_local_transport import LocalActorTransport
from ..subagents.actor_mailbox import ActorMailboxStore
from ..subagents.actor_registry import ActorExecutionRegistry
from ..subagents.actor_transport import ActorSpawnSpec
from ..subagents.remote_dispatch import resolve_git_revision
from ..subagents.remote_types import RemoteTaskRequest


class TaskToolMixin:
    def _get_local_actor_transport(self) -> LocalActorTransport:
        transport = getattr(self, "_local_actor_transport", None)
        if isinstance(transport, LocalActorTransport):
            return transport
        registry = ActorExecutionRegistry()
        mailbox_store = ActorMailboxStore()
        transport = LocalActorTransport(registry=registry, mailbox_store=mailbox_store)
        self.actor_registry = registry
        self.actor_mailbox_store = mailbox_store
        self._local_actor_transport = transport
        return transport

    def _task_child_result(
        self,
        *,
        tool_use_id: str,
        agent: str,
        child_session_id: str,
        child_final_text: str,
        child_stop_reason: str | None,
        dispatch_mode: str,
        target_node: str | None = None,
        git_revision: str | None = None,
        worker_execution_id: str | None = None,
        execution_id: str | None = None,
    ) -> ToolResult:
        payload: dict[str, Any] = {
            "child_session_id": child_session_id,
            "final_text": child_final_text,
            "child_stop_reason": child_stop_reason,
            "dispatch_mode": dispatch_mode,
        }
        if isinstance(execution_id, str) and execution_id:
            payload["execution_id"] = execution_id
        if isinstance(target_node, str) and target_node:
            payload["target_node"] = target_node
        if isinstance(git_revision, str) and git_revision:
            payload["git_revision"] = git_revision
        if isinstance(worker_execution_id, str) and worker_execution_id:
            payload["worker_execution_id"] = worker_execution_id

        final_text = child_final_text.strip()
        stop_reason = child_stop_reason or ("end" if final_text else "missing_result")
        if stop_reason != "end" or not final_text:
            reason_suffix = f"stop_reason={stop_reason}"
            if not final_text:
                message = f"Subagent '{agent}' finished without output ({reason_suffix})"
                error_type = "SubagentNoOutput"
            else:
                message = f"Subagent '{agent}' finished abnormally ({reason_suffix})"
                error_type = "SubagentFailed"
            return ToolResult(
                tool_use_id=tool_use_id,
                output=payload,
                is_error=True,
                error_type=error_type,
                error_message=message,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )

        return ToolResult(
            tool_use_id=tool_use_id,
            output=payload,
            is_error=False,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )

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
                child_stop_reason: str | None = None
                async for child_event in handle.events:
                    store.append_event(session_id, child_event)
                    yield child_event
                    if isinstance(child_event, Result):
                        child_final_text = child_event.final_text
                        child_stop_reason = child_event.stop_reason

                result = self._task_child_result(
                    tool_use_id=tool_call.tool_use_id,
                    agent=agent,
                    child_session_id=handle.child_session_id,
                    child_final_text=child_final_text,
                    child_stop_reason=child_stop_reason,
                    dispatch_mode="k3s",
                    target_node=handle.target_node,
                    git_revision=handle.git_revision,
                    worker_execution_id=handle.worker_execution_id,
                    execution_id=handle.execution_id,
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

        execution_id = uuid.uuid4().hex
        child_session_id = store.create_session(
            metadata={
                "parent_session_id": session_id,
                "parent_tool_use_id": tool_call.tool_use_id,
                "agent_name": agent,
                "dispatch_mode": "local",
                "execution_id": execution_id,
            }
        )
        child_options = OpenAgenticOptions(
            provider=definition.provider or options.provider,
            model=definition.model or options.model,
            api_key=(
                definition.provider_spec.api_key
                if getattr(definition.provider_spec, "api_key", None)
                else options.api_key
            ),
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
        transport = self._get_local_actor_transport()
        handle = await transport.spawn(
            ActorSpawnSpec(
                execution_id=execution_id,
                parent_actor_id=self._agent_name or "host",
                child_actor_id=f"{agent}/{execution_id}",
                agent_name=agent,
                dispatch_mode="local",
                child_session_id=child_session_id,
                run=lambda _control_messages: child_runtime.query(combined_prompt),
            )
        )
        child_final_text = ""
        child_stop_reason: str | None = None
        async for envelope in transport.receive(handle):
            payload = envelope.payload if isinstance(envelope.payload, dict) else {}
            child_event = payload.get("event")
            if isinstance(child_event, dict):
                child_event = event_from_dict(child_event)
            store.append_event(session_id, child_event)
            yield child_event
            if isinstance(child_event, Result):
                child_final_text = child_event.final_text
                child_stop_reason = child_event.stop_reason
        await transport.close(handle)

        result = self._task_child_result(
            tool_use_id=tool_call.tool_use_id,
            agent=agent,
            child_session_id=child_session_id,
            child_final_text=child_final_text,
            child_stop_reason=child_stop_reason,
            dispatch_mode="local",
            execution_id=execution_id,
        )
        store.append_event(session_id, result)
        yield result


