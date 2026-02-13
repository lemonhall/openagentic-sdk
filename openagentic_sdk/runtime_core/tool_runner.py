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

class ToolRunnerMixin:
    async def _run_tool_call(
        self,
        *,
        session_id: str,
        tool_call: ToolCall,
        store: FileSessionStore,
        hooks: HookEngine,
    ) -> AsyncIterator[Any]:
        options = self._options
        tool_name = tool_call.name
        tool_input: Mapping[str, Any] = tool_call.arguments

        allowed_tools = options.allowed_tools
        if allowed_tools is not None and tool_name not in set(allowed_tools):
            denied = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="ToolNotAllowed",
                error_message=f"Tool '{tool_name}' is not allowed",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, denied)
            yield denied
            return

        use_event = ToolUse(
            tool_use_id=tool_call.tool_use_id,
            name=tool_name,
            input=tool_input,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, use_event)
        yield use_event

        ctx = {"session_id": session_id, "tool_use_id": tool_call.tool_use_id, "agent_name": self._agent_name}
        tool_input2, hook_events, decision = await hooks.run_pre_tool_use(
            tool_name=tool_name,
            tool_input=tool_input,
            context=ctx,
        )
        for he in hook_events:
            store.append_event(session_id, he)
            yield he
        if decision is not None and decision.block:
            blocked = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="HookBlocked",
                error_message=decision.block_reason or "blocked by hook",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, blocked)
            yield blocked
            return

        approval = await options.permission_gate.approve(tool_name, tool_input2, context=ctx)
        if approval.question is not None:
            store.append_event(session_id, approval.question)
            yield approval.question
        if not approval.allowed:
            denied = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="PermissionDenied",
                error_message=approval.deny_message or "tool use not approved",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, denied)
            yield denied
            return
        tool_input2 = approval.updated_input or tool_input2

        if tool_name == "AskUserQuestion":
            async for ev in self._handle_ask_user_question(
                session_id=session_id,
                tool_call=tool_call,
                tool_input=tool_input2,
                store=store,
            ):
                yield ev
            return

        if tool_name == "Task":
            async for ev in self._handle_task_tool(
                session_id=session_id,
                tool_call=tool_call,
                tool_input=tool_input2,
                store=store,
            ):
                yield ev
            return

        if tool_name == "SlashCommand":
            try:
                name = tool_input2.get("name")
                args = tool_input2.get("args", tool_input2.get("arguments", ""))
                if not isinstance(name, str) or not name:
                    raise ValueError("SlashCommand: 'name' must be a non-empty string")
                if not isinstance(args, str):
                    args = str(args)
                rendered, sources, parts = await self._render_slash_command(
                    session_id=session_id,
                    tool_use_id=tool_call.tool_use_id,
                    name=name,
                    args=args,
                )
                output: dict[str, Any] = {
                    "name": name,
                    "args": args,
                    "sources": sources,
                    "content": rendered,
                    "parts": parts,
                }
                output2, post_events, post_decision = await hooks.run_post_tool_use(
                    tool_name=tool_name,
                    tool_output=output,
                    context=ctx,
                )
                for he in post_events:
                    store.append_event(session_id, he)
                    yield he
                if post_decision is not None and post_decision.block:
                    raise RuntimeError(post_decision.block_reason or "blocked by hook")
                result = ToolResult(
                    tool_use_id=tool_call.tool_use_id,
                    output=output2,
                    is_error=False,
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )
            except Exception as e:  # noqa: BLE001
                result = ToolResult(
                    tool_use_id=tool_call.tool_use_id,
                    output=None,
                    is_error=True,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )

            store.append_event(session_id, result)
            yield result
            return

        if tool_name == "WebFetch":
            prompt_text = tool_input2.get("prompt")
            if isinstance(prompt_text, str) and prompt_text:
                async for ev in self._handle_webfetch_prompt(
                    session_id=session_id,
                    tool_call=tool_call,
                    tool_input=tool_input2,
                    store=store,
                    hooks=hooks,
                    ctx=ctx,
                ):
                    yield ev
                return

        if tool_name == "TodoWrite":
            async for ev in self._handle_todowrite(
                session_id=session_id,
                tool_call=tool_call,
                tool_input=tool_input2,
                store=store,
                hooks=hooks,
                ctx=ctx,
            ):
                yield ev
            return

        try:
            tool = options.tools.get(tool_name)
            output = await tool.run(tool_input2, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
            output2, post_events, post_decision = await hooks.run_post_tool_use(
                tool_name=tool_name,
                tool_output=output,
                context=ctx,
            )
            for he in post_events:
                store.append_event(session_id, he)
                yield he
            if post_decision is not None and post_decision.block:
                raise RuntimeError(post_decision.block_reason or "blocked by hook")
            output = output2
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=output,
                is_error=False,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
        except Exception as e:  # noqa: BLE001
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type=type(e).__name__,
                error_message=str(e),
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )

        store.append_event(session_id, result)
        yield result

