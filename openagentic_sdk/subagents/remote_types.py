from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from ..options import AgentDefinition


@dataclass(frozen=True, slots=True)
class RemoteTaskDispatchHandle:
    child_session_id: str
    target_node: str
    git_revision: str
    worker_execution_id: str | None
    events: AsyncIterator[Any]

    @property
    def execution_id(self) -> str | None:
        return self.worker_execution_id


@dataclass(frozen=True, slots=True)
class RemoteTaskRequest:
    parent_session_id: str
    parent_tool_use_id: str
    agent_name: str
    prompt: str
    definition: AgentDefinition
    cwd: str
    project_dir: str | None
    git_revision: str
    worker_execution_id: str | None = None

    def make_handle(
        self,
        *,
        child_session_id: str,
        target_node: str,
        git_revision: str,
        worker_execution_id: str | None = None,
        events: AsyncIterator[Any],
    ) -> RemoteTaskDispatchHandle:
        return RemoteTaskDispatchHandle(
            child_session_id=child_session_id,
            target_node=target_node,
            git_revision=git_revision,
            worker_execution_id=worker_execution_id,
            events=events,
        )


class RemoteTaskDispatcher(Protocol):
    async def dispatch(self, request: RemoteTaskRequest) -> RemoteTaskDispatchHandle: ...
