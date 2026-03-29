from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from openagentic_sdk.events import AssistantMessage
from openagentic_sdk.options import AgentDefinition, AgentExecutorDefinition, AgentWorkspaceDefinition
from openagentic_sdk.serialization import event_to_dict
from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = None
        self.terminated = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        return 0

    def kill(self) -> None:
        self.terminated = True


class TestK3dDispatcher(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_preserves_actor_down_from_http_transport(self) -> None:
        from openagentic_sdk.subagents.k3d_dispatcher import K3dPortForwardRemoteTaskDispatcher

        proc = _FakeProc()

        class FakeHttpRemoteTaskDispatcher:
            def __init__(self, *, base_url: str, timeout_s: float) -> None:
                _ = (base_url, timeout_s)

            async def dispatch(self, request: RemoteTaskRequest):
                async def _envelopes():
                    yield ActorEnvelope(
                        protocol_version="v1",
                        message_id="msg-1",
                        execution_id="exec-k3d-1",
                        sender_actor_id="worker_remote/exec-k3d-1",
                        recipient_actor_id="host",
                        mailbox="child_events",
                        seq=1,
                        kind="child_event",
                        payload={
                            "event": event_to_dict(
                                AssistantMessage(
                                    text="remote child started",
                                    agent_name=request.agent_name,
                                    parent_tool_use_id=request.parent_tool_use_id,
                                )
                            )
                        },
                        ts=1.0,
                    )
                    yield ActorEnvelope(
                        protocol_version="v1",
                        message_id="msg-2",
                        execution_id="exec-k3d-1",
                        sender_actor_id="worker_remote/exec-k3d-1",
                        recipient_actor_id="host",
                        mailbox="child_events",
                        seq=2,
                        kind="down",
                        payload=ActorDownEvent(
                            execution_id="exec-k3d-1",
                            actor_id="worker_remote/exec-k3d-1",
                            reason_kind="remote_worker_error",
                            reason_detail="ValueError: bad parse",
                            final_state="failed",
                            dispatch_mode="k3s",
                            child_session_id="child-k3d-1",
                            target_node=request.definition.executor.node_name,
                            worker_execution_id="exec-k3d-1",
                        ).to_payload(),
                        ts=2.0,
                    )

                return request.make_handle(
                    child_session_id="child-k3d-1",
                    target_node=request.definition.executor.node_name or "",
                    git_revision=request.git_revision,
                    worker_execution_id="exec-k3d-1",
                    envelopes=_envelopes(),
                )

        dispatcher = K3dPortForwardRemoteTaskDispatcher(namespace="openagentic-v56")
        request = RemoteTaskRequest(
            parent_session_id="p" * 32,
            parent_tool_use_id="call_task",
            agent_name="worker_remote",
            prompt="Do remote child work",
            definition=AgentDefinition(
                description="remote child",
                prompt="REMOTE_CHILD_DEF",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            ),
            cwd="E:/fake/repo",
            project_dir="E:/fake/repo",
            git_revision="rev-k3d-1",
        )

        with mock.patch("openagentic_sdk.subagents.k3d_dispatcher.HttpRemoteTaskDispatcher", FakeHttpRemoteTaskDispatcher):
            with mock.patch("openagentic_sdk.subagents.k3d_dispatcher.subprocess.Popen", return_value=proc):
                with mock.patch.object(dispatcher, "_resolve_worker_pod_name", return_value="pod-a"):
                    with mock.patch.object(dispatcher, "_pick_free_local_port", return_value=18765):
                        with mock.patch.object(dispatcher, "_wait_for_port_forward", return_value=None):
                            handle = await dispatcher.dispatch(request)
                            child_events = [event async for event in handle.events]
                            down = await asyncio.wait_for(handle.down_future, timeout=1.0)

        self.assertEqual(len(child_events), 1)
        self.assertEqual(getattr(child_events[0], "text", None), "remote child started")
        self.assertEqual(down.reason_kind, "remote_worker_error")
        self.assertTrue(proc.terminated)


if __name__ == "__main__":
    unittest.main()
