from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

from ..events import Result
from ..options import AgentDefinition
from ..serialization import event_from_dict
from .actor_lifecycle import ActorDownEvent, classify_child_result_down, classify_remote_exception_down
from .actor_protocol import ActorEnvelope


@dataclass(frozen=True, slots=True)
class RemoteTaskDispatchHandle:
    child_session_id: str
    target_node: str
    git_revision: str
    worker_execution_id: str | None
    events: AsyncIterator[Any]
    down_future: asyncio.Future[ActorDownEvent]
    envelopes: AsyncIterator[ActorEnvelope] | None = None
    sender: Callable[[ActorEnvelope], Awaitable[None]] | None = None
    acker: Callable[[ActorEnvelope], Awaitable[None]] | None = None
    aborter: Callable[[], Awaitable[None]] | None = None
    closer: Callable[[], Awaitable[None]] | None = None

    @property
    def execution_id(self) -> str | None:
        return self.worker_execution_id

    async def abort(self) -> None:
        if self.aborter is not None:
            await self.aborter()

    async def send(self, envelope: ActorEnvelope) -> None:
        if self.sender is not None:
            await self.sender(envelope)
            return
        if envelope.kind == "abort":
            await self.abort()
            return
        raise RuntimeError("remote task handle does not support send")

    async def ack(self, envelope: ActorEnvelope) -> None:
        if self.acker is not None:
            await self.acker(envelope)

    async def close(self) -> None:
        if self.closer is not None:
            await self.closer()


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
        events: AsyncIterator[Any] | None = None,
        envelopes: AsyncIterator[ActorEnvelope] | None = None,
        sender: Callable[[ActorEnvelope], Awaitable[None]] | None = None,
        acker: Callable[[ActorEnvelope], Awaitable[None]] | None = None,
        aborter: Callable[[], Awaitable[None]] | None = None,
        closer: Callable[[], Awaitable[None]] | None = None,
    ) -> RemoteTaskDispatchHandle:
        if events is None and envelopes is None:
            raise ValueError("remote task handle requires events or envelopes")
        execution_id = worker_execution_id or child_session_id
        loop = asyncio.get_running_loop()
        down_future: asyncio.Future[ActorDownEvent] = loop.create_future()

        async def _event_stream(stream: AsyncIterator[Any]) -> AsyncIterator[Any]:
            last_result: Result | None = None
            try:
                async for event in stream:
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

        if envelopes is not None:
            async def _tracked_envelopes() -> AsyncIterator[ActorEnvelope]:
                try:
                    async for envelope in envelopes:
                        if envelope.kind == "down" and isinstance(envelope.payload, dict):
                            _resolve_down(down_future, ActorDownEvent.from_payload(envelope.payload))
                        yield envelope
                        if acker is not None:
                            await acker(envelope)
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
                    if not down_future.done():
                        _resolve_down(
                            down_future,
                            classify_child_result_down(
                                execution_id=execution_id,
                                actor_id=self.agent_name,
                                dispatch_mode=self.definition.executor.kind,
                                result=None,
                                child_session_id=child_session_id,
                                target_node=target_node,
                                worker_execution_id=worker_execution_id,
                            ),
                        )

            tracked_envelopes = _tracked_envelopes()

            async def _events_from_envelopes() -> AsyncIterator[Any]:
                async for envelope in tracked_envelopes:
                    if envelope.kind != "child_event":
                        continue
                    payload = envelope.payload if isinstance(envelope.payload, dict) else {}
                    raw_event = payload.get("event")
                    if isinstance(raw_event, dict):
                        yield event_from_dict(raw_event)

            return RemoteTaskDispatchHandle(
                child_session_id=child_session_id,
                target_node=target_node,
                git_revision=git_revision,
                worker_execution_id=worker_execution_id,
                events=_events_from_envelopes(),
                down_future=down_future,
                envelopes=tracked_envelopes,
                sender=sender,
                acker=acker,
                aborter=aborter,
                closer=closer,
            )

        return RemoteTaskDispatchHandle(
            child_session_id=child_session_id,
            target_node=target_node,
            git_revision=git_revision,
            worker_execution_id=worker_execution_id,
            events=_event_stream(events),
            down_future=down_future,
            sender=sender,
            acker=acker,
            aborter=aborter,
            closer=closer,
        )


class RemoteTaskDispatcher(Protocol):
    async def dispatch(self, request: RemoteTaskRequest) -> RemoteTaskDispatchHandle: ...


def _resolve_down(future: asyncio.Future[ActorDownEvent], down: ActorDownEvent) -> None:
    if not future.done():
        future.set_result(down)
