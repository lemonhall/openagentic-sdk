from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

from .actor_protocol import ActorEnvelope


@dataclass(frozen=True, slots=True)
class ActorExecutionHandle:
    execution_id: str
    actor_id: str
    child_session_id: str | None
    event_mailbox: str = "child_events"
    control_mailbox: str = "control"


@dataclass(frozen=True, slots=True)
class ActorSpawnSpec:
    execution_id: str
    parent_actor_id: str
    child_actor_id: str
    agent_name: str
    dispatch_mode: str
    child_session_id: str | None
    run: Callable[[AsyncIterator[ActorEnvelope]], AsyncIterator[Any] | Awaitable[AsyncIterator[Any]]]
    event_mailbox: str = "child_events"
    control_mailbox: str = "control"


class ActorTransport(Protocol):
    async def spawn(self, spec: ActorSpawnSpec) -> ActorExecutionHandle: ...

    async def send(self, handle: ActorExecutionHandle, envelope: ActorEnvelope) -> None: ...

    def receive(self, handle: ActorExecutionHandle) -> AsyncIterator[ActorEnvelope]: ...

    async def abort(self, handle: ActorExecutionHandle) -> None: ...

    async def close(self, handle: ActorExecutionHandle) -> None: ...
