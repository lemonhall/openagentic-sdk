from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from ..events import Result
from ..options import AgentDefinition
from .actor_lifecycle import ActorDownEvent, classify_child_result_down, classify_remote_exception_down


@dataclass(frozen=True, slots=True)
class RemoteTaskDispatchHandle:
    child_session_id: str
    target_node: str
    git_revision: str
    worker_execution_id: str | None
    events: AsyncIterator[Any]
    down_future: asyncio.Future[ActorDownEvent]

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
        execution_id = worker_execution_id or child_session_id
        loop = asyncio.get_running_loop()
        down_future: asyncio.Future[ActorDownEvent] = loop.create_future()

        async def _events() -> AsyncIterator[Any]:
            last_result: Result | None = None
            try:
                async for event in events:
                    if isinstance(event, Result):
                        last_result = event
                    yield event
            except Exception as exc:  # noqa: BLE001
                _resolve_down(
                    down_future,
                    classify_remote_exception_down(
                        execution_id=execution_id,
                        actor_id=self.agent_name,
                        dispatch_mode=self.definition.executor.kind,
                        exc=exc,
                        child_session_id=child_session_id,
                        target_node=target_node,
                        worker_execution_id=worker_execution_id,
                    ),
                )
                raise
            else:
                _resolve_down(
                    down_future,
                    classify_child_result_down(
                        execution_id=execution_id,
                        actor_id=self.agent_name,
                        dispatch_mode=self.definition.executor.kind,
                        result=last_result,
                        child_session_id=child_session_id,
                        target_node=target_node,
                        worker_execution_id=worker_execution_id,
                    ),
                )

        return RemoteTaskDispatchHandle(
            child_session_id=child_session_id,
            target_node=target_node,
            git_revision=git_revision,
            worker_execution_id=worker_execution_id,
            events=_events(),
            down_future=down_future,
        )


class RemoteTaskDispatcher(Protocol):
    async def dispatch(self, request: RemoteTaskRequest) -> RemoteTaskDispatchHandle: ...


def _resolve_down(future: asyncio.Future[ActorDownEvent], down: ActorDownEvent) -> None:
    if not future.done():
        future.set_result(down)
