from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from ..options import OpenAgenticOptions
from ..sessions.store import FileSessionStore
from .actor_local_transport import LocalActorTransport
from .actor_mailbox import ActorMailboxStore
from .actor_protocol import ActorEnvelope
from .actor_registry import ActorExecutionRegistry
from .actor_tracing import ensure_actor_tracing
from .actor_transport import ActorSpawnSpec
from .readonly_policy import build_remote_allowed_tools
from .remote_types import RemoteTaskDispatchHandle, RemoteTaskRequest
from .session_meta import build_child_session_metadata


@dataclass(slots=True)
class InProcessRemoteTaskWorker:
    base_options: OpenAgenticOptions
    session_store: FileSessionStore
    last_child_session_id: str | None = field(default=None, init=False)

    async def dispatch(self, request: RemoteTaskRequest) -> RemoteTaskDispatchHandle:
        execution_id = request.worker_execution_id or uuid.uuid4().hex
        tracing = ensure_actor_tracing(self.base_options)
        child_session_id = self.session_store.create_session(
            metadata=build_child_session_metadata(
                parent_session_id=request.parent_session_id,
                parent_tool_use_id=request.parent_tool_use_id,
                agent_name=request.agent_name,
                dispatch_mode=request.definition.executor.kind,
                target_node=request.definition.executor.node_name,
                git_revision=request.git_revision,
                worker_execution_id=execution_id,
            )
        )
        self.last_child_session_id = child_session_id

        child_options = OpenAgenticOptions(
            provider=request.definition.provider or self.base_options.provider,
            model=request.definition.model or self.base_options.model,
            api_key=(
                request.definition.provider_spec.api_key
                if getattr(request.definition.provider_spec, "api_key", None)
                else self.base_options.api_key
            ),
            cwd=request.cwd,
            max_steps=self.base_options.max_steps,
            timeout_s=self.base_options.timeout_s,
            include_partial_messages=self.base_options.include_partial_messages,
            abort_event=self.base_options.abort_event,
            tools=self.base_options.tools,
            allowed_tools=build_remote_allowed_tools(
                request.definition,
                fallback_allowed_tools=self.base_options.allowed_tools,
            ),
            permission_gate=self.base_options.permission_gate,
            hooks=self.base_options.hooks,
            session_store=self.session_store,
            session_root=self.base_options.session_root,
            resume=child_session_id,
            resume_max_events=self.base_options.resume_max_events,
            resume_max_bytes=self.base_options.resume_max_bytes,
            setting_sources=self.base_options.setting_sources,
            project_dir=request.project_dir,
            system_prompt=self.base_options.system_prompt,
            instruction_files=self.base_options.instruction_files,
            compaction=self.base_options.compaction,
            agents=self.base_options.agents,
            remote_task_dispatcher=self.base_options.remote_task_dispatcher,
            mcp_servers=self.base_options.mcp_servers,
            mcp_registry=self.base_options.mcp_registry,
        )

        from ..runtime_core.agent_runtime import AgentRuntime

        child_runtime = AgentRuntime(
            child_options,
            agent_name=request.agent_name,
            parent_tool_use_id=request.parent_tool_use_id,
        )
        combined_prompt = request.definition.prompt + "\n\n" + request.prompt
        child_actor_id = f"{request.agent_name}/{execution_id}"
        actor_state: dict[str, object] = {}

        async def _ensure_actor():
            transport = actor_state.get("transport")
            handle = actor_state.get("handle")
            mailbox_store = actor_state.get("mailbox_store")
            if isinstance(transport, LocalActorTransport) and handle is not None and isinstance(mailbox_store, ActorMailboxStore):
                return transport, handle, mailbox_store

            registry = ActorExecutionRegistry()
            mailbox_store = ActorMailboxStore()
            transport = LocalActorTransport(registry=registry, mailbox_store=mailbox_store, tracing=tracing)
            handle = await transport.spawn(
                ActorSpawnSpec(
                    execution_id=execution_id,
                    parent_actor_id="remote-host",
                    child_actor_id=child_actor_id,
                    agent_name=request.agent_name,
                    dispatch_mode=request.definition.executor.kind,
                    child_session_id=child_session_id,
                    run=lambda _control_messages: child_runtime.query(combined_prompt),
                    trace_context=request.trace_context,
                    trace_links=(request.trace_context,) if request.trace_context else (),
                    parent_session_id=request.parent_session_id,
                    target_node=request.definition.executor.node_name,
                )
            )
            actor_state["transport"] = transport
            actor_state["handle"] = handle
            actor_state["mailbox_store"] = mailbox_store
            return transport, handle, mailbox_store

        async def _envelopes():
            transport, handle, mailbox_store = await _ensure_actor()
            try:
                async for envelope in transport.receive(handle):
                    yield envelope
                down = await handle.down_future
                yield ActorEnvelope(
                    protocol_version="v1",
                    message_id=uuid.uuid4().hex,
                    execution_id=execution_id,
                    sender_actor_id=child_actor_id,
                    recipient_actor_id="remote-host",
                    mailbox=handle.event_mailbox,
                    seq=mailbox_store.next_seq(execution_id, handle.event_mailbox),
                    kind="down",
                    payload=down.to_payload(),
                    ts=asyncio.get_running_loop().time(),
                )
            finally:
                await transport.close(handle)

        async def _abort() -> None:
            transport, handle, _mailbox_store = await _ensure_actor()
            await transport.abort(handle)

        async def _send(envelope: ActorEnvelope) -> None:
            transport, handle, _mailbox_store = await _ensure_actor()
            await transport.send(handle, envelope)

        async def _close() -> None:
            transport = actor_state.get("transport")
            handle = actor_state.get("handle")
            if isinstance(transport, LocalActorTransport) and handle is not None:
                await transport.close(handle)

        return request.make_handle(
            child_session_id=child_session_id,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id=execution_id,
            envelopes=_envelopes(),
            sender=_send,
            aborter=_abort,
            closer=_close,
        )
