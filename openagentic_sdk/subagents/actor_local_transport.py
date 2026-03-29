from __future__ import annotations

import asyncio
import contextlib
import inspect
import uuid
from dataclasses import dataclass
from typing import AsyncIterator

from ..serialization import event_to_dict
from .actor_mailbox import ActorMailboxStore
from .actor_protocol import ActorEnvelope
from .actor_registry import ActorExecutionRegistry
from .actor_transport import ActorExecutionHandle, ActorSpawnSpec


@dataclass
class _LocalExecutionState:
    handle: ActorExecutionHandle
    queue: asyncio.Queue[ActorEnvelope | object]
    control_queue: asyncio.Queue[ActorEnvelope | object]
    task: asyncio.Task[None]


class LocalActorTransport:
    def __init__(self, *, registry: ActorExecutionRegistry, mailbox_store: ActorMailboxStore) -> None:
        self._registry = registry
        self._mailbox_store = mailbox_store
        self._executions: dict[str, _LocalExecutionState] = {}
        self._done_sentinel = object()

    async def spawn(self, spec: ActorSpawnSpec) -> ActorExecutionHandle:
        self._registry.register_execution(
            execution_id=spec.execution_id,
            agent_name=spec.agent_name,
            dispatch_mode="local",
        )
        self._registry.update_state(spec.execution_id, "running")
        handle = ActorExecutionHandle(
            execution_id=spec.execution_id,
            actor_id=spec.child_actor_id,
            child_session_id=spec.child_session_id,
            event_mailbox=spec.event_mailbox,
            control_mailbox=spec.control_mailbox,
        )
        queue: asyncio.Queue[ActorEnvelope | object] = asyncio.Queue()
        control_queue: asyncio.Queue[ActorEnvelope | object] = asyncio.Queue()
        task = asyncio.create_task(self._run_child(spec, queue, control_queue), name=f"local-actor-{spec.execution_id}")
        self._executions[spec.execution_id] = _LocalExecutionState(
            handle=handle,
            queue=queue,
            control_queue=control_queue,
            task=task,
        )
        return handle

    async def send(self, handle: ActorExecutionHandle, envelope: ActorEnvelope) -> None:
        state = self._executions.get(handle.execution_id)
        if state is None:
            raise KeyError(f"unknown execution_id: {handle.execution_id}")
        self._mailbox_store.append(envelope)
        self._registry.record_mailbox_head(
            handle.execution_id,
            mailbox=envelope.mailbox,
            seq=self._mailbox_store.head_seq(handle.execution_id, envelope.mailbox),
        )
        await state.control_queue.put(envelope)

    async def abort(self, handle: ActorExecutionHandle) -> None:
        state = self._executions.get(handle.execution_id)
        if state is None:
            return
        await state.control_queue.put(self._done_sentinel)
        state.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.task
        self._registry.update_state(handle.execution_id, "aborted")

    async def close(self, handle: ActorExecutionHandle) -> None:
        state = self._executions.get(handle.execution_id)
        if state is None:
            return
        await asyncio.shield(state.task)

    async def _run_child(
        self,
        spec: ActorSpawnSpec,
        queue: asyncio.Queue[ActorEnvelope | object],
        control_queue: asyncio.Queue[ActorEnvelope | object],
    ) -> None:
        try:
            stream = spec.run(self._control_stream(control_queue))
            if inspect.isawaitable(stream):
                stream = await stream
            async for event in stream:
                envelope = ActorEnvelope(
                    protocol_version="v1",
                    message_id=uuid.uuid4().hex,
                    execution_id=spec.execution_id,
                    sender_actor_id=spec.child_actor_id,
                    recipient_actor_id=spec.parent_actor_id,
                    mailbox=spec.event_mailbox,
                    seq=self._mailbox_store.next_seq(spec.execution_id, spec.event_mailbox),
                    kind="child_event",
                    payload={"event": event_to_dict(event)},
                    ts=asyncio.get_running_loop().time(),
                )
                self._mailbox_store.append(envelope)
                self._registry.record_mailbox_head(
                    spec.execution_id,
                    mailbox=spec.event_mailbox,
                    seq=self._mailbox_store.head_seq(spec.execution_id, spec.event_mailbox),
                )
                await queue.put(envelope)
            self._registry.update_state(spec.execution_id, "exited")
        except asyncio.CancelledError:
            self._registry.update_state(spec.execution_id, "aborted")
            raise
        except Exception:
            self._registry.update_state(spec.execution_id, "failed")
        finally:
            await queue.put(self._done_sentinel)
            await control_queue.put(self._done_sentinel)

    async def receive(self, handle: ActorExecutionHandle) -> AsyncIterator[ActorEnvelope]:
        state = self._executions.get(handle.execution_id)
        if state is None:
            raise KeyError(f"unknown execution_id: {handle.execution_id}")
        while True:
            item = await state.queue.get()
            if item is self._done_sentinel:
                break
            yield item

    async def _control_stream(self, queue: asyncio.Queue[ActorEnvelope | object]) -> AsyncIterator[ActorEnvelope]:
        while True:
            item = await queue.get()
            if item is self._done_sentinel:
                break
            yield item
