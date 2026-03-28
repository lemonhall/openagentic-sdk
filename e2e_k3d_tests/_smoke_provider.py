from __future__ import annotations

import os

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
