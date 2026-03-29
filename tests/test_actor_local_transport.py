from __future__ import annotations

import asyncio
import unittest

from openagentic_sdk.events import AssistantMessage, Result
from openagentic_sdk.serialization import event_from_dict


class TestActorLocalTransport(unittest.IsolatedAsyncioTestCase):
    async def test_spawn_streams_child_events_and_updates_registry(self) -> None:
        from openagentic_sdk.subagents.actor_local_transport import LocalActorTransport
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore
        from openagentic_sdk.subagents.actor_registry import ActorExecutionRegistry
        from openagentic_sdk.subagents.actor_transport import ActorSpawnSpec

        registry = ActorExecutionRegistry()
        mailbox_store = ActorMailboxStore()
        transport = LocalActorTransport(registry=registry, mailbox_store=mailbox_store)
        started = asyncio.Event()
        release = asyncio.Event()

        async def run_child(_control_messages):
            started.set()
            yield AssistantMessage(text="child started", agent_name="worker", parent_tool_use_id="call_task")
            await release.wait()
            yield Result(
                final_text="child ok",
                session_id="child-session",
                stop_reason="end",
                agent_name="worker",
                parent_tool_use_id="call_task",
            )

        handle = await transport.spawn(
            ActorSpawnSpec(
                execution_id="exec-1",
                parent_actor_id="host",
                child_actor_id="worker/exec-1",
                agent_name="worker",
                dispatch_mode="local",
                child_session_id="child-session",
                run=run_child,
            )
        )

        await asyncio.wait_for(started.wait(), timeout=1.0)
        self.assertEqual(registry.get("exec-1").state, "running")

        release.set()
        envelopes = []
        async for envelope in transport.receive(handle):
            envelopes.append(envelope)

        await transport.close(handle)

        self.assertEqual(handle.execution_id, "exec-1")
        self.assertEqual(handle.child_session_id, "child-session")
        self.assertEqual([env.kind for env in envelopes], ["child_event", "child_event"])
        self.assertIsInstance(envelopes[0].payload["event"], dict)
        self.assertIsInstance(envelopes[1].payload["event"], dict)
        self.assertEqual(event_from_dict(envelopes[0].payload["event"]).text, "child started")
        self.assertEqual(event_from_dict(envelopes[1].payload["event"]).final_text, "child ok")
        self.assertEqual(mailbox_store.head_seq("exec-1", "child_events"), 2)
        self.assertEqual(registry.get("exec-1").mailbox_heads["child_events"], 2)
        self.assertEqual(registry.get("exec-1").state, "exited")

    async def test_send_delivers_control_envelope_to_child(self) -> None:
        from openagentic_sdk.subagents.actor_local_transport import LocalActorTransport
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore
        from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
        from openagentic_sdk.subagents.actor_registry import ActorExecutionRegistry
        from openagentic_sdk.subagents.actor_transport import ActorSpawnSpec

        registry = ActorExecutionRegistry()
        mailbox_store = ActorMailboxStore()
        transport = LocalActorTransport(registry=registry, mailbox_store=mailbox_store)

        async def run_child(control_messages):
            control = await anext(control_messages)
            yield AssistantMessage(
                text=f"got {control.payload['op']}",
                agent_name="worker",
                parent_tool_use_id="call_task",
            )

        handle = await transport.spawn(
            ActorSpawnSpec(
                execution_id="exec-2",
                parent_actor_id="host",
                child_actor_id="worker/exec-2",
                agent_name="worker",
                dispatch_mode="local",
                child_session_id="child-session",
                run=run_child,
            )
        )

        envelopes = []
        receive_task = asyncio.create_task(_collect_events(transport, handle, envelopes))

        await transport.send(
            handle,
            ActorEnvelope(
                protocol_version="v1",
                message_id="ctrl-1",
                execution_id="exec-2",
                sender_actor_id="host",
                recipient_actor_id="worker/exec-2",
                mailbox="control",
                seq=1,
                kind="control",
                payload={"op": "noop"},
                ts=1.0,
            ),
        )
        await transport.close(handle)
        await receive_task

        self.assertEqual(mailbox_store.head_seq("exec-2", "control"), 1)
        self.assertEqual(registry.get("exec-2").mailbox_heads["control"], 1)
        self.assertEqual(len(envelopes), 1)
        self.assertEqual(event_from_dict(envelopes[0].payload["event"]).text, "got noop")


async def _collect_events(transport, handle, out):  # noqa: ANN001
    async for envelope in transport.receive(handle):
        out.append(envelope)


if __name__ == "__main__":
    unittest.main()
