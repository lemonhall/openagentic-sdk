from __future__ import annotations

import asyncio
import json
import os

from e2e_k3d_tests._harness import AGENT_A_NODE, AGENT_B_NODE
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
)
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

        if isinstance(user_text, str) and "REMOTE_RESEARCH_DEF" in user_text:
            topic = _extract_suffix(user_text, "RESEARCH_SLICE::") or _extract_suffix(user_text, "RESEARCH_TOPIC::") or "general"
            if "RESEARCH_SLICE::" in user_text:
                await asyncio.sleep(1.0)
            return ModelOutput(
                assistant_text=f"RESEARCH_OK[{topic}] on {node_name}",
                tool_calls=[],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and "REMOTE_WRITER_DEF" in user_text:
            topic = _extract_suffix(user_text, "WRITER_DRAFT::") or "general"
            return ModelOutput(
                assistant_text=f"WRITER_OK[{topic}] on {node_name}",
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
        last_user_index = max((index for index, message in enumerate(messages) if message.get("role") == "user"), default=-1)
        turn_messages = messages[last_user_index + 1 :]
        tool_outputs = _decode_turn_tool_outputs(turn_messages)

        if isinstance(user_text, str) and _is_greeting(user_text) and not tool_outputs:
            return ModelOutput(assistant_text="你好，我可以先研究资料，再整理成摘要。", tool_calls=[], usage=None, raw=None)

        if isinstance(user_text, str) and _is_fanout_request(user_text):
            fanout_ids = ("research_fanout_1", "research_fanout_2", "research_fanout_3", "research_fanout_4")
            if not any(call_id in tool_outputs for call_id in fanout_ids):
                return ModelOutput(
                    assistant_text=None,
                    tool_calls=[
                        ToolCall(
                            tool_use_id=call_id,
                            name="Task",
                            arguments={"agent": "research", "prompt": f"RESEARCH_SLICE::direction-{index + 1}"},
                        )
                        for index, call_id in enumerate(fanout_ids)
                    ],
                    usage=None,
                    raw=None,
                )
            summary = " | ".join(
                _task_final_text(tool_outputs.get(call_id)) or f"missing:{call_id}"
                for call_id in fanout_ids
            )
            return ModelOutput(assistant_text=f"FANOUT_SUMMARY {summary}", tool_calls=[], usage=None, raw=None)

        if isinstance(user_text, str) and _is_serial_research_then_write(user_text):
            if "research_step" not in tool_outputs:
                return ModelOutput(
                    assistant_text=None,
                    tool_calls=[
                        ToolCall(
                            tool_use_id="research_step",
                            name="Task",
                            arguments={"agent": "research", "prompt": f"RESEARCH_TOPIC::{user_text}"},
                        )
                    ],
                    usage=None,
                    raw=None,
                )
            if "writer_step" not in tool_outputs:
                research_summary = _task_final_text(tool_outputs.get("research_step")) or "research-missing"
                return ModelOutput(
                    assistant_text=None,
                    tool_calls=[
                        ToolCall(
                            tool_use_id="writer_step",
                            name="Task",
                            arguments={"agent": "writer", "prompt": f"WRITER_DRAFT::{research_summary}"},
                        )
                    ],
                    usage=None,
                    raw=None,
                )
            writer_summary = _task_final_text(tool_outputs.get("writer_step")) or "writer-missing"
            return ModelOutput(assistant_text=f"SERIAL_ROUTE_OK {writer_summary}", tool_calls=[], usage=None, raw=None)

        if isinstance(user_text, str) and _is_research_request(user_text) and "research_step" not in tool_outputs:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="research_step",
                        name="Task",
                        arguments={"agent": "research", "prompt": f"RESEARCH_TOPIC::{user_text}"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and _is_research_request(user_text) and "research_step" in tool_outputs:
            return ModelOutput(
                assistant_text=f"RESEARCH_ROUTE_OK {_task_final_text(tool_outputs.get('research_step')) or 'missing'}",
                tool_calls=[],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and _is_writer_request(user_text) and "writer_step" not in tool_outputs:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="writer_step",
                        name="Task",
                        arguments={"agent": "writer", "prompt": f"WRITER_DRAFT::{user_text}"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and _is_writer_request(user_text) and "writer_step" in tool_outputs:
            return ModelOutput(
                assistant_text=f"WRITER_ROUTE_OK {_task_final_text(tool_outputs.get('writer_step')) or 'missing'}",
                tool_calls=[],
                usage=None,
                raw=None,
            )

        return ModelOutput(assistant_text="我可以帮你研究资料、并行拆分研究方向，或者基于研究结果整理摘要。", tool_calls=[], usage=None, raw=None)


def create_host_provider() -> K3dSmokeHostProvider:
    return K3dSmokeHostProvider()


def create_cluster_agents() -> dict[str, AgentDefinition]:
    return {
        "research": AgentDefinition(
            description="研究型 remote subagent，擅长搜索、阅读、整理资料，固定运行在 agent-0。",
            prompt="REMOTE_RESEARCH_DEF",
            tools=("Read", "WebSearch"),
            executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_A_NODE),
            workspace=AgentWorkspaceDefinition(mode="readonly"),
            worker=AgentWorkerDefinition(max_concurrent_tasks=3),
        ),
        "writer": AgentDefinition(
            description="写作型 remote subagent，擅长把研究结果整理成摘要或短稿，固定运行在 agent-1。",
            prompt="REMOTE_WRITER_DEF",
            tools=("Read",),
            executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_B_NODE),
            workspace=AgentWorkspaceDefinition(mode="readonly"),
            worker=AgentWorkerDefinition(max_concurrent_tasks=3),
        ),
    }


def _extract_suffix(text: str, marker: str) -> str | None:
    if marker not in text:
        return None
    return text.split(marker, 1)[1].strip()


def _is_greeting(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("你好", "hello", "hi", "hey"))


def _is_research_request(text: str) -> bool:
    return any(token in text for token in ("研究", "调研", "搜索", "资料"))


def _is_writer_request(text: str) -> bool:
    return any(token in text for token in ("写", "摘要", "文章", "整理成稿"))


def _is_serial_research_then_write(text: str) -> bool:
    return _is_research_request(text) and _is_writer_request(text) and any(token in text for token in ("先", "再", "然后"))


def _is_fanout_request(text: str) -> bool:
    return any(token in text for token in ("并行研究", "并发研究", "多个方向", "四个方向"))


def _decode_turn_tool_outputs(turn_messages) -> dict[str, object]:
    outputs: dict[str, object] = {}
    for message in turn_messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        tool_call_id = message.get("tool_call_id")
        content = message.get("content")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        if not isinstance(content, str):
            outputs[tool_call_id] = None
            continue
        try:
            outputs[tool_call_id] = json.loads(content)
        except json.JSONDecodeError:
            outputs[tool_call_id] = None
    return outputs


def _task_final_text(raw_payload: object) -> str | None:
    if isinstance(raw_payload, dict):
        final_text = raw_payload.get("final_text")
        if isinstance(final_text, str) and final_text:
            return final_text
    return None
