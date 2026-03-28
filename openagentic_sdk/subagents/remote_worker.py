from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..options import OpenAgenticOptions
from ..sessions.store import FileSessionStore
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
            api_key=self.base_options.api_key,
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

        async def _events():
            async for event in child_runtime.query(combined_prompt):
                yield event

        return request.make_handle(
            child_session_id=child_session_id,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id=execution_id,
            events=_events(),
        )
