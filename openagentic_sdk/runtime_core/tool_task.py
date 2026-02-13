from __future__ import annotations

import inspect
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Sequence

from .._version import __version__ as _SDK_VERSION
from ..events import (
    AssistantDelta,
    AssistantMessage,
    Result,
    SystemInit,
    ToolOutputCompacted,
    ToolResult,
    ToolUse,
    UserMessage,
    UserCompaction,
    UserQuestion,
)
from ..hooks.engine import HookEngine
from ..mcp.sdk import McpSdkServerConfig, wrap_sdk_server_tools
from ..mcp.client import StdioMcpClient
from ..mcp.remote_client import RemoteMcpClient
from ..mcp.wrappers import (
    wrap_http_mcp_prompts,
    wrap_http_mcp_resources,
    wrap_http_mcp_tools,
    wrap_stdio_mcp_prompts,
    wrap_stdio_mcp_resources,
    wrap_stdio_mcp_tools,
)
from ..options import OpenAgenticOptions
from ..paths import default_session_root
from ..prompt_system import BuiltSystemPrompt, build_system_prompt
from ..compaction import (
    COMPACTION_MARKER_QUESTION,
    COMPACTION_SYSTEM_PROMPT,
    COMPACTION_USER_INSTRUCTION,
    TOOL_OUTPUT_PLACEHOLDER,
    select_tool_outputs_to_prune,
    would_overflow,
)
from ..providers.base import ModelOutput, ToolCall
from ..sessions.rebuild import rebuild_messages, rebuild_responses_input
from ..sessions.store import FileSessionStore
from ..skills.index import index_skills
from ..tools.base import ToolContext
from ..tools.openai import tool_schemas_for_openai
from ..tools.openai_responses import tool_schemas_for_responses
from ..tools.task import TaskTool
from ..commands import load_command_template
from ..opencode_markdown import FILE_REGEX

import shlex
import asyncio
import uuid


from .common import (
    _base_system_role_for_model,
    _build_project_system_prompt,
    _callable_accepts_kw,
    _default_session_root,
    _detect_provider_protocol,
    _extract_function_call_outputs,
    _filter_supported_kwargs,
    _looks_like_outputs_without_calls,
    _maybe_expand_execute_skill_prompt,
    _maybe_expand_list_skills_prompt,
    _no_tool_call_found_for_call_output_error,
    _prepend_function_calls_for_responses,
    _tool_result_payload,
    _unsupported_previous_response_id_error,
)

class TaskToolMixin:
    async def _handle_task_tool(
        self,
        *,
        session_id: str,
        tool_call: ToolCall,
        tool_input: Mapping[str, Any],
        store: FileSessionStore,
    ) -> AsyncIterator[Any]:
        options = self._options

        agent = tool_input.get("agent")
        task_prompt = tool_input.get("prompt")
        if not isinstance(agent, str) or not agent:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="InvalidTaskInput",
                error_message="Task: 'agent' must be a non-empty string",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return
        if not isinstance(task_prompt, str) or not task_prompt:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="InvalidTaskInput",
                error_message="Task: 'prompt' must be a non-empty string",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        definition = options.agents.get(agent)
        if definition is None:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="UnknownAgent",
                error_message=f"Unknown agent '{agent}'",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        child_session_id = store.create_session(
            metadata={
                "parent_session_id": session_id,
                "parent_tool_use_id": tool_call.tool_use_id,
                "agent_name": agent,
            }
        )
        child_options = OpenAgenticOptions(
            provider=definition.provider or options.provider,
            model=definition.model or options.model,
            api_key=options.api_key,
            cwd=options.cwd,
            max_steps=options.max_steps,
            timeout_s=options.timeout_s,
            tools=options.tools,
            allowed_tools=list(definition.tools) if definition.tools else options.allowed_tools,
            permission_gate=options.permission_gate,
            hooks=options.hooks,
            session_store=store,
            resume=child_session_id,
            setting_sources=options.setting_sources,
            agents=options.agents,
        )

        # AgentRuntime lived in the same module pre-refactor; import lazily to
        # avoid circular imports during module initialization.
        from .agent_runtime import AgentRuntime

        child_runtime = AgentRuntime(child_options, agent_name=agent, parent_tool_use_id=tool_call.tool_use_id)
        combined_prompt = definition.prompt + "\n\n" + task_prompt
        child_final_text = ""
        async for child_event in child_runtime.query(combined_prompt):
            store.append_event(session_id, child_event)
            yield child_event
            if isinstance(child_event, Result):
                child_final_text = child_event.final_text

        result = ToolResult(
            tool_use_id=tool_call.tool_use_id,
            output={"child_session_id": child_session_id, "final_text": child_final_text},
            is_error=False,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, result)
        yield result


