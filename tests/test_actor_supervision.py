from __future__ import annotations

import asyncio
import unittest


class TestActorSupervision(unittest.IsolatedAsyncioTestCase):
    async def test_local_transport_emits_structured_down_for_normal_exit(self) -> None:
        from openagentic_sdk.events import Result
        from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
        from openagentic_sdk.subagents.actor_local_transport import LocalActorTransport
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore
        from openagentic_sdk.subagents.actor_registry import ActorExecutionRegistry
        from openagentic_sdk.subagents.actor_transport import ActorSpawnSpec

        registry = ActorExecutionRegistry()
        transport = LocalActorTransport(registry=registry, mailbox_store=ActorMailboxStore())

        async def run_child(_control_messages):
            yield Result(final_text="ok", session_id="child-session", stop_reason="end")

        handle = await transport.spawn(
            ActorSpawnSpec(
                execution_id="exec-normal",
                parent_actor_id="host",
                child_actor_id="worker/exec-normal",
                agent_name="worker",
                dispatch_mode="local",
                child_session_id="child-session",
                run=run_child,
            )
        )

        async for _ in transport.receive(handle):
            pass
        await transport.close(handle)

        down = await asyncio.wait_for(handle.down_future, timeout=1.0)
        self.assertIsInstance(down, ActorDownEvent)
        self.assertEqual(down.reason_kind, "normal")
        self.assertEqual(down.final_state, "exited")
        self.assertEqual(registry.get("exec-normal").last_down, down)

    async def test_local_transport_emits_structured_down_for_child_error(self) -> None:
        from openagentic_sdk.events import AssistantMessage
        from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
        from openagentic_sdk.subagents.actor_local_transport import LocalActorTransport
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore
        from openagentic_sdk.subagents.actor_registry import ActorExecutionRegistry
        from openagentic_sdk.subagents.actor_transport import ActorSpawnSpec

        registry = ActorExecutionRegistry()
        transport = LocalActorTransport(registry=registry, mailbox_store=ActorMailboxStore())

        async def run_child(_control_messages):
            yield AssistantMessage(text="before boom")
            raise RuntimeError("boom")

        handle = await transport.spawn(
            ActorSpawnSpec(
                execution_id="exec-failed",
                parent_actor_id="host",
                child_actor_id="worker/exec-failed",
                agent_name="worker",
                dispatch_mode="local",
                child_session_id="child-session",
                run=run_child,
            )
        )

        async for _ in transport.receive(handle):
            pass
        await transport.close(handle)

        down = await asyncio.wait_for(handle.down_future, timeout=1.0)
        self.assertIsInstance(down, ActorDownEvent)
        self.assertEqual(down.reason_kind, "child_exit_error")
        self.assertEqual(down.final_state, "failed")
        self.assertIn("boom", down.reason_detail or "")
        self.assertEqual(registry.get("exec-failed").last_down, down)

    async def test_local_transport_emits_structured_down_for_abort(self) -> None:
        from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
        from openagentic_sdk.subagents.actor_local_transport import LocalActorTransport
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore
        from openagentic_sdk.subagents.actor_registry import ActorExecutionRegistry
        from openagentic_sdk.subagents.actor_transport import ActorSpawnSpec

        registry = ActorExecutionRegistry()
        transport = LocalActorTransport(registry=registry, mailbox_store=ActorMailboxStore())
        started = asyncio.Event()

        async def run_child(_control_messages):
            started.set()
            await asyncio.Event().wait()
            yield None

        handle = await transport.spawn(
            ActorSpawnSpec(
                execution_id="exec-aborted",
                parent_actor_id="host",
                child_actor_id="worker/exec-aborted",
                agent_name="worker",
                dispatch_mode="local",
                child_session_id="child-session",
                run=run_child,
            )
        )

        await asyncio.wait_for(started.wait(), timeout=1.0)
        await transport.abort(handle)
        await transport.close(handle)

        down = await asyncio.wait_for(handle.down_future, timeout=1.0)
        self.assertIsInstance(down, ActorDownEvent)
        self.assertEqual(down.reason_kind, "aborted")
        self.assertEqual(down.final_state, "aborted")
        self.assertEqual(registry.get("exec-aborted").last_down, down)

    def test_supervisor_retry_once_on_transport_loss_retries_once(self) -> None:
        from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
        from openagentic_sdk.subagents.actor_supervisor import ActorSupervisor

        down = ActorDownEvent(
            execution_id="exec-1",
            actor_id="worker/exec-1",
            reason_kind="transport_lost",
            reason_detail="socket reset",
            final_state="failed",
            dispatch_mode="k3s",
        )

        first = ActorSupervisor.decide(
            policy="retry_once_on_transport_loss",
            down=down,
            retry_count=0,
        )
        second = ActorSupervisor.decide(
            policy="retry_once_on_transport_loss",
            down=down,
            retry_count=1,
        )

        self.assertEqual(first.action, "retry")
        self.assertEqual(second.action, "fail_parent_tool_use")

    def test_supervisor_does_not_treat_child_exit_error_as_transport_loss(self) -> None:
        from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
        from openagentic_sdk.subagents.actor_supervisor import ActorSupervisor

        down = ActorDownEvent(
            execution_id="exec-1",
            actor_id="worker/exec-1",
            reason_kind="child_exit_error",
            reason_detail="no_output",
            final_state="failed",
            dispatch_mode="local",
        )

        decision = ActorSupervisor.decide(
            policy="retry_once_on_transport_loss",
            down=down,
            retry_count=0,
        )

        self.assertEqual(decision.action, "fail_parent_tool_use")


if __name__ == "__main__":
    unittest.main()
