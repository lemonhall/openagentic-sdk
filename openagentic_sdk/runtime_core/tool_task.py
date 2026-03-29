from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Mapping

from ..events import Result, ToolResult
from ..options import OpenAgenticOptions
from ..providers.base import ToolCall
from ..serialization import event_from_dict
from ..sessions.store import FileSessionStore
from ..subagents.actor_lifecycle import ActorDownEvent
from ..subagents.actor_local_transport import LocalActorTransport
from ..subagents.actor_mailbox import ActorMailboxStore
from ..subagents.actor_registry import ActorExecutionRegistry
from ..subagents.actor_supervisor import ActorSupervisor, SupervisorDecision
from ..subagents.actor_transport import ActorSpawnSpec
from ..subagents.remote_dispatch import resolve_git_revision
from ..subagents.remote_types import RemoteTaskDispatchHandle, RemoteTaskRequest

_STREAM_END = object()


@dataclass(slots=True)
class _AttemptOutcome:
    child_final_text: str = ""
    child_stop_reason: str | None = None
    down: ActorDownEvent | None = None
    abort_consumed: bool = False


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
        runtime_state = getattr(getattr(self, "_options", None), "runtime_state", None)
        if runtime_state is not None:
            runtime_state.bind_runtime(self)
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
        down: ActorDownEvent,
        supervisor: SupervisorDecision,
        target_node: str | None = None,
        git_revision: str | None = None,
        worker_execution_id: str | None = None,
        execution_id: str | None = None,
    ) -> ToolResult:
        effective_stop_reason = child_stop_reason or ("end" if child_final_text.strip() and down.reason_kind == "normal" else "missing_result")
        payload: dict[str, Any] = {
            "child_session_id": child_session_id,
            "final_text": child_final_text,
            "child_stop_reason": effective_stop_reason,
            "dispatch_mode": dispatch_mode,
            "down": down.to_payload(),
            "supervisor": supervisor.to_payload(),
        }
        if isinstance(execution_id, str) and execution_id:
            payload["execution_id"] = execution_id
        if isinstance(target_node, str) and target_node:
            payload["target_node"] = target_node
        if isinstance(git_revision, str) and git_revision:
            payload["git_revision"] = git_revision
        if isinstance(worker_execution_id, str) and worker_execution_id:
            payload["worker_execution_id"] = worker_execution_id

        if down.reason_kind == "normal" and child_final_text.strip():
            return ToolResult(
                tool_use_id=tool_use_id,
                output=payload,
                is_error=False,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )

        error_type, error_message = self._task_error_for_down(
            agent=agent,
            down=down,
            child_final_text=child_final_text,
            child_stop_reason=effective_stop_reason,
        )
        return ToolResult(
            tool_use_id=tool_use_id,
            output=payload,
            is_error=True,
            error_type=error_type,
            error_message=error_message,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )

    def _task_error_for_down(
        self,
        *,
        agent: str,
        down: ActorDownEvent,
        child_final_text: str,
        child_stop_reason: str | None,
    ) -> tuple[str, str]:
        stop_reason = child_stop_reason or "missing_result"
        final_text = child_final_text.strip()
        if down.reason_kind == "transport_lost":
            return "SubagentTransportLost", f"Subagent '{agent}' transport lost ({down.reason_detail or 'transport_lost'})"
        if down.reason_kind == "remote_worker_error":
            return "RemoteWorkerError", f"Subagent '{agent}' remote worker failed ({down.reason_detail or down.reason_kind})"
        if down.reason_kind == "aborted":
            return "SubagentAborted", f"Subagent '{agent}' was aborted ({down.reason_detail or down.reason_kind})"
        if stop_reason != "end" or not final_text:
            reason_suffix = f"stop_reason={stop_reason}"
            if not final_text:
                return "SubagentNoOutput", f"Subagent '{agent}' finished without output ({reason_suffix})"
            return "SubagentFailed", f"Subagent '{agent}' finished abnormally ({reason_suffix})"
        return "SubagentFailed", f"Subagent '{agent}' failed ({down.reason_detail or down.reason_kind})"

    async def _iter_remote_attempt(
        self,
        *,
        session_id: str,
        store: FileSessionStore,
        handle: RemoteTaskDispatchHandle,
        outcome: _AttemptOutcome,
    ) -> AsyncIterator[Any]:
        try:
            async for child_event in handle.events:
                store.append_event(session_id, child_event)
                yield child_event
                if isinstance(child_event, Result):
                    outcome.child_final_text = child_event.final_text
                    outcome.child_stop_reason = child_event.stop_reason
        except Exception:  # noqa: BLE001
            pass
        outcome.down = await handle.down_future
        self._record_remote_down(outcome.down)

    async def _iter_local_attempt(
        self,
        *,
        session_id: str,
        store: FileSessionStore,
        transport: LocalActorTransport,
        handle,
        outcome: _AttemptOutcome,
    ) -> AsyncIterator[Any]:
        receive_iter = transport.receive(handle)
        next_task = asyncio.create_task(anext(receive_iter, _STREAM_END))
        abort_task = asyncio.create_task(self._wait_for_abort_event()) if self._should_watch_abort() else None
        try:
            while True:
                pending = {next_task}
                if abort_task is not None:
                    pending.add(abort_task)
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                if abort_task is not None and abort_task in done:
                    outcome.abort_consumed = True
                    next_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await next_task
                    await transport.abort(handle)
                    break
                if next_task not in done:
                    continue
                envelope = next_task.result()
                if envelope is _STREAM_END:
                    break
                payload = envelope.payload if isinstance(envelope.payload, dict) else {}
                child_event = payload.get("event")
                if isinstance(child_event, dict):
                    child_event = event_from_dict(child_event)
                if child_event is None:
                    next_task = asyncio.create_task(anext(receive_iter, _STREAM_END))
                    continue
                store.append_event(session_id, child_event)
                yield child_event
                if isinstance(child_event, Result):
                    outcome.child_final_text = child_event.final_text
                    outcome.child_stop_reason = child_event.stop_reason
                next_task = asyncio.create_task(anext(receive_iter, _STREAM_END))
        finally:
            next_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await next_task
            if abort_task is not None:
                abort_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await abort_task
            await transport.close(handle)
        outcome.down = await handle.down_future

    def _record_remote_execution(self, *, execution_id: str | None, agent: str, handle: RemoteTaskDispatchHandle) -> None:
        if not isinstance(execution_id, str) or not execution_id:
            return
        registry = getattr(self, "actor_registry", None)
        if not isinstance(registry, ActorExecutionRegistry):
            return
        try:
            registry.register_execution(
                execution_id=execution_id,
                agent_name=agent,
                dispatch_mode="k3s",
                target_node=handle.target_node,
                worker_execution_id=handle.worker_execution_id,
            )
        except ValueError:
            pass
        registry.update_state(execution_id, "running")

    def _record_remote_down(self, down: ActorDownEvent) -> None:
        registry = getattr(self, "actor_registry", None)
        if not isinstance(registry, ActorExecutionRegistry):
            return
        with contextlib.suppress(KeyError):
            registry.record_down(down.execution_id, down)

    def _task_dispatch_failure_result(
        self,
        *,
        tool_use_id: str,
        agent: str,
        dispatch_mode: str,
        git_revision: str | None,
        target_node: str | None,
        execution_id: str,
        exc: BaseException,
        supervisor_policy: str,
        retry_count: int,
    ) -> tuple[ToolResult, SupervisorDecision]:
        down = self._classify_dispatch_failure_down(
            execution_id=execution_id,
            agent=agent,
            dispatch_mode=dispatch_mode,
            target_node=target_node,
            exc=exc,
        )
        decision = ActorSupervisor.decide(policy=supervisor_policy, down=down, retry_count=retry_count)
        return (
            self._task_child_result(
                tool_use_id=tool_use_id,
                agent=agent,
                child_session_id="",
                child_final_text="",
                child_stop_reason=None,
                dispatch_mode=dispatch_mode,
                down=down,
                supervisor=decision,
                target_node=target_node,
                git_revision=git_revision,
                worker_execution_id=execution_id,
                execution_id=execution_id,
            ),
            decision,
        )

    def _classify_dispatch_failure_down(
        self,
        *,
        execution_id: str,
        agent: str,
        dispatch_mode: str,
        target_node: str | None,
        exc: BaseException,
    ) -> ActorDownEvent:
        from ..subagents.actor_lifecycle import classify_remote_exception_down

        return classify_remote_exception_down(
            execution_id=execution_id,
            actor_id=agent,
            dispatch_mode=dispatch_mode,
            exc=exc,
            target_node=target_node,
            worker_execution_id=execution_id,
        )

    def _supervisor_policy(self, agent: str) -> str:
        definition = self._options.agents.get(agent)
        if definition is None:
            return "fail_parent_tool_use"
        policy = getattr(definition.worker, "supervisor_policy", None)
        return policy if isinstance(policy, str) and policy else "fail_parent_tool_use"

    def _should_watch_abort(self) -> bool:
        abort_event = getattr(self._options, "abort_event", None)
        return abort_event is not None and callable(getattr(abort_event, "is_set", None))

    def _clear_abort_event(self) -> None:
        abort_event = getattr(self._options, "abort_event", None)
        clear = getattr(abort_event, "clear", None)
        if callable(clear):
            clear()

    async def _wait_for_abort_event(self) -> bool:
        abort_event = getattr(self._options, "abort_event", None)
        if abort_event is None:
            await asyncio.Future()
        while not getattr(abort_event, "is_set", lambda: False)():
            await asyncio.sleep(0.05)
        return True

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

        supervisor_policy = self._supervisor_policy(agent)
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

            git_revision = resolve_git_revision(cwd=options.cwd)
            retry_count = 0
            remote_execution_id = uuid.uuid4().hex
            while True:
                request = RemoteTaskRequest(
                    parent_session_id=session_id,
                    parent_tool_use_id=tool_call.tool_use_id,
                    agent_name=agent,
                    prompt=task_prompt,
                    definition=definition,
                    cwd=options.cwd,
                    project_dir=options.project_dir,
                    git_revision=git_revision,
                    worker_execution_id=remote_execution_id,
                )
                try:
                    handle = await dispatcher.dispatch(request)
                except Exception as exc:  # noqa: BLE001
                    result, decision = self._task_dispatch_failure_result(
                        tool_use_id=tool_call.tool_use_id,
                        agent=agent,
                        dispatch_mode="k3s",
                        git_revision=git_revision,
                        target_node=definition.executor.node_name,
                        execution_id=remote_execution_id,
                        exc=exc,
                        supervisor_policy=supervisor_policy,
                        retry_count=retry_count,
                    )
                    if decision.action == "retry":
                        retry_count += 1
                        continue
                    store.append_event(session_id, result)
                    yield result
                    return

                self._record_remote_execution(execution_id=handle.execution_id, agent=agent, handle=handle)

                outcome = _AttemptOutcome()
                async for child_event in self._iter_remote_attempt(
                    session_id=session_id,
                    store=store,
                    handle=handle,
                    outcome=outcome,
                ):
                    yield child_event
                down = outcome.down
                if down is None:
                    raise RuntimeError("remote attempt completed without down event")
                decision = ActorSupervisor.decide(policy=supervisor_policy, down=down, retry_count=retry_count)
                if decision.action == "retry":
                    retry_count += 1
                    continue

                result = self._task_child_result(
                    tool_use_id=tool_call.tool_use_id,
                    agent=agent,
                    child_session_id=handle.child_session_id,
                    child_final_text=outcome.child_final_text,
                    child_stop_reason=outcome.child_stop_reason,
                    dispatch_mode="k3s",
                    down=down,
                    supervisor=decision,
                    target_node=handle.target_node,
                    git_revision=handle.git_revision,
                    worker_execution_id=handle.worker_execution_id,
                    execution_id=handle.execution_id,
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
            abort_event=options.abort_event,
            tools=options.tools,
            allowed_tools=list(definition.tools) if definition.tools else options.allowed_tools,
            permission_gate=options.permission_gate,
            hooks=options.hooks,
            session_store=store,
            resume=child_session_id,
            setting_sources=options.setting_sources,
            agents=options.agents,
        )

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

        outcome = _AttemptOutcome()
        async for child_event in self._iter_local_attempt(
            session_id=session_id,
            store=store,
            transport=transport,
            handle=handle,
            outcome=outcome,
        ):
            yield child_event
        down = outcome.down
        if down is None:
            raise RuntimeError("local attempt completed without down event")
        if outcome.abort_consumed:
            self._clear_abort_event()
        decision = ActorSupervisor.decide(policy=supervisor_policy, down=down, retry_count=0)
        result = self._task_child_result(
            tool_use_id=tool_call.tool_use_id,
            agent=agent,
            child_session_id=child_session_id,
            child_final_text=outcome.child_final_text,
            child_stop_reason=outcome.child_stop_reason,
            dispatch_mode="local",
            down=down,
            supervisor=decision,
            execution_id=execution_id,
        )
        store.append_event(session_id, result)
        yield result
