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

class WebFetchPromptMixin:
    async def _handle_webfetch_prompt(
        self,
        *,
        session_id: str,
        tool_call: ToolCall,
        tool_input: Mapping[str, Any],
        store: FileSessionStore,
        hooks: HookEngine,
        ctx: Mapping[str, Any],
    ) -> AsyncIterator[Any]:
        options = self._options
        tool_name = tool_call.name

        prompt_text = tool_input.get("prompt")
        if not isinstance(prompt_text, str) or not prompt_text:
            return

        try:
            tool = options.tools.get(tool_name)
            fetched = await tool.run(tool_input, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
            page_text = fetched.get("text", "") if isinstance(fetched, dict) else ""
            if not isinstance(page_text, str):
                page_text = str(page_text)

            complete_fn: Any = getattr(options.provider, "complete")
            protocol = _detect_provider_protocol(options.provider)
            prompt_msg = {"role": "user", "content": f"{prompt_text}\n\nCONTENT:\n{page_text}"}
            if protocol == "legacy":
                kwargs = {
                    "model": options.model,
                    "messages": [prompt_msg],
                    "tools": (),
                    "api_key": options.api_key,
                }
            else:
                kwargs = {
                    "model": options.model,
                    "input": [prompt_msg],
                    "tools": (),
                    "api_key": options.api_key,
                    "store": True,
                }
            model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
            response = model_out.assistant_text or ""

            output: dict[str, Any] = {
                "response": response,
                "url": fetched.get("url") if isinstance(fetched, dict) else tool_input.get("url"),
                "final_url": fetched.get("url") if isinstance(fetched, dict) else None,
                "status_code": fetched.get("status") if isinstance(fetched, dict) else None,
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


