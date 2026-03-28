from __future__ import annotations

import os

from e2e_k3d_tests._harness import AGENT_A_NODE, AGENT_B_NODE
from openagentic_sdk.options import AgentDefinition, AgentExecutorDefinition, AgentWorkspaceDefinition
from openagentic_sdk.providers.base import ModelOutput, ToolCall


class K3dSmokeWorkerProvider:
    name = "k3d-smoke-worker"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        has_tool_output = any(m.get("role") == "tool" for m in messages)
        node_name = os.environ.get("OA_REMOTE_NODE_NAME", "unknown-node")

        if isinstance(user_text, str) and "TRY_WRITE" in user_text and not has_tool_output:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="write_1",
                        name="Write",
                        arguments={"file_path": "README.md", "content": "blocked"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and "TRY_WRITE" in user_text:
            return ModelOutput(
                assistant_text=f"WRITE_BLOCKED on {node_name}",
                tool_calls=[],
                usage=None,
                raw=None,
            )

        return ModelOutput(
            assistant_text=f"REMOTE_OK on {node_name}",
            tool_calls=[],
            usage=None,
            raw=None,
        )


def create_worker_provider() -> K3dSmokeWorkerProvider:
    return K3dSmokeWorkerProvider()


class K3dSmokeHostProvider:
    name = "k3d-smoke-host"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
        user_text = user_messages[-1] if user_messages else ""
        has_tool_output = any(m.get("role") == "tool" for m in messages)

        if user_text == "TASK_A" and not has_tool_output:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker_a", "prompt": "REPORT_NODE"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if user_text == "TASK_B" and not has_tool_output:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker_b", "prompt": "REPORT_NODE"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if has_tool_output:
            return ModelOutput(assistant_text="CHAT_HOST_TASK_OK", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="CHAT_HOST_OK", tool_calls=[], usage=None, raw=None)


def create_host_provider() -> K3dSmokeHostProvider:
    return K3dSmokeHostProvider()


def create_cluster_agents() -> dict[str, AgentDefinition]:
    return {
        "worker_a": AgentDefinition(
            description="k3d host worker a",
            prompt="REMOTE_K3D_DEF",
            tools=("Read",),
            executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_A_NODE),
            workspace=AgentWorkspaceDefinition(mode="readonly"),
        ),
        "worker_b": AgentDefinition(
            description="k3d host worker b",
            prompt="REMOTE_K3D_DEF",
            tools=("Read",),
            executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_B_NODE),
            workspace=AgentWorkspaceDefinition(mode="readonly"),
        ),
    }
