from __future__ import annotations

import inspect
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Sequence

from ._version import __version__ as _SDK_VERSION
from .events import (
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
from .hooks.engine import HookEngine
from .mcp.sdk import McpSdkServerConfig, wrap_sdk_server_tools
from .mcp.client import StdioMcpClient
from .mcp.remote_client import RemoteMcpClient
from .mcp.wrappers import (
    wrap_http_mcp_prompts,
    wrap_http_mcp_resources,
    wrap_http_mcp_tools,
    wrap_stdio_mcp_prompts,
    wrap_stdio_mcp_resources,
    wrap_stdio_mcp_tools,
)
from .options import OpenAgenticOptions
from .paths import default_session_root
from .prompt_system import BuiltSystemPrompt, build_system_prompt
from .compaction import (
    COMPACTION_MARKER_QUESTION,
    COMPACTION_SYSTEM_PROMPT,
    COMPACTION_USER_INSTRUCTION,
    TOOL_OUTPUT_PLACEHOLDER,
    select_tool_outputs_to_prune,
    would_overflow,
)
from .providers.base import ModelOutput, ToolCall
from .sessions.rebuild import rebuild_messages, rebuild_responses_input
from .sessions.store import FileSessionStore
from .skills.index import index_skills
from .tools.base import ToolContext
from .tools.openai import tool_schemas_for_openai
from .tools.openai_responses import tool_schemas_for_responses
from .tools.task import TaskTool
from .commands import load_command_template
from .opencode_markdown import FILE_REGEX

import shlex
import asyncio
import uuid


def _callable_accepts_kw(fn: Any, name: str) -> bool:
    try:
        sig = inspect.signature(fn)
    except Exception:  # noqa: BLE001
        return False
    if name in sig.parameters:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def _tool_result_payload(ev: "ToolResult") -> Any:
    # Provider protocols only get `output`, so on errors we must serialize the
    # error fields too (otherwise the model sees `null`).
    if not getattr(ev, "is_error", False):
        return getattr(ev, "output", None)
    return {
        "is_error": True,
        "error_type": getattr(ev, "error_type", None),
        "error_message": getattr(ev, "error_message", None),
        "output": getattr(ev, "output", None),
    }


def _filter_supported_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop kwargs a callable doesn't accept.

    This avoids runtime TypeErrors and lets custom providers implement only a
    subset of the Responses API keyword surface.
    """

    try:
        sig = inspect.signature(fn)
    except Exception:  # noqa: BLE001
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    allowed = set(sig.parameters.keys())
    return {k: v for k, v in kwargs.items() if k in allowed}


def _detect_provider_protocol(provider: Any) -> str:
    """Best-effort protocol detection based on provider call signatures.

    We prefer to detect via `complete()` (used for non-streaming providers), but
    fall back to `stream()` when a provider only supports streaming.
    """

    for attr in ("complete", "stream"):
        fn = getattr(provider, attr, None)
        if fn is None:
            continue
        try:
            sig = inspect.signature(fn)
        except Exception:  # noqa: BLE001
            continue
        params = sig.parameters
        if "input" in params:
            return "responses"
        if "messages" in params:
            return "legacy"
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            # Prefer modern protocol when the provider is flexible.
            return "responses"

    return "responses"


def _default_session_root() -> Path:
    return default_session_root()


def _build_project_system_prompt(options: OpenAgenticOptions) -> BuiltSystemPrompt:
    """Backwards-compatible wrapper.

    The system prompt builder now returns both the system text and any
    Responses-level `instructions` (used for Codex OAuth sessions).
    """

    return build_system_prompt(options)


def _base_system_role_for_model(*, model_id: str, provider_protocol: str) -> str:
    if provider_protocol != "responses":
        return "system"
    mid = (model_id or "").lower()
    # Match OpenCode's openai-compatible Responses adapter defaults:
    # reasoning families prefer developer role.
    if mid.startswith("o") or "gpt-5" in mid or mid.startswith("codex-") or mid.startswith("computer-use"):
        return "developer"
    return "system"


_EXEC_SKILL_RE = re.compile(
    r"^\s*(?:执行技能|运行技能|run skill|execute skill)\s*[:：]?\s*([A-Za-z0-9_.-]+)\s*$",
    re.IGNORECASE,
)

_LIST_SKILLS_RE = re.compile(
    r"^\s*(?:what\s+skills\s+are\s+available\??|list\s+skills|有哪些技能\??|有什么技能\??|技能有哪些\??)\s*$",
    re.IGNORECASE,
)


def _maybe_expand_execute_skill_prompt(prompt: str, options: OpenAgenticOptions) -> str:
    """
    Best-effort helper for users who type "执行技能<name>" expecting an automatic skill run.

    If the prompt matches and the skill exists on disk, instruct the model to load it via the
    `Skill` tool and follow the Workflow/Checklist without asking for extra input.
    """
    m = _EXEC_SKILL_RE.match(prompt or "")
    if not m:
        return prompt

    skill_name = m.group(1)
    project_dir = options.project_dir or options.cwd
    skills = index_skills(project_dir=project_dir)
    match = next((s for s in skills if s.name == skill_name), None)
    if match is None:
        return prompt

    return (
        f"你正在执行技能 `{skill_name}`。\n"
        "除非技能文档明确要求，否则不要向用户询问额外的目标/输入。\n"
        "请严格按技能的 Workflow/Checklist 执行。\n\n"
        f'你 MUST 调用 `Skill` 工具加载该技能：`Skill({{"name": "{skill_name}"}})`。\n'
    )


def _maybe_expand_list_skills_prompt(prompt: str, options: OpenAgenticOptions) -> str:
    """
    Best-effort helper for users who ask to list available skills without explicitly naming the tool.
    """
    if not _LIST_SKILLS_RE.match(prompt or ""):
        return prompt

    # If there are no skills, keep the prompt as-is.
    project_dir = options.project_dir or options.cwd
    skills = index_skills(project_dir=project_dir)
    if not skills:
        return prompt

    return (
        "List the available Skills for this project.\n"
        "The available skills are listed in the `Skill` tool description under <available_skills>.\n"
        "Present them as a short bullet list: `name` — description (or summary).\n"
    )


def _unsupported_previous_response_id_error(e: BaseException) -> bool:
    msg = str(e)
    if not msg:
        return False
    msg_l = msg.lower()
    return "previous_response_id" in msg_l and ("unsupported parameter" in msg_l or "unsupported" in msg_l)


def _no_tool_call_found_for_call_output_error(e: BaseException) -> bool:
    msg = str(e)
    if not msg:
        return False
    msg_l = msg.lower()
    return "no tool call found for function call output" in msg_l and "call_id" in msg_l


def _extract_function_call_outputs(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Extract Responses tool outputs from an input list.

    Some hook pipelines may prepend role-based messages (system/developer) even
    when the runtime is in Responses incremental mode and is trying to send only
    `function_call_output` items.

    For retry/fallback logic we want to:
    - detect when the input effectively contains only tool outputs (plus optional
      system/developer role messages)
    - re-send a combined `function_call` + `function_call_output` input without
      accidentally placing role-based items in the middle of Responses items.
    """

    outs: list[Mapping[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("type") == "function_call_output":
            outs.append(it)
    return outs


def _looks_like_outputs_without_calls(items: Sequence[Mapping[str, Any]]) -> bool:
    """True when `items` contains tool outputs but no matching tool calls.

    We allow role-based system/developer messages to be present (some hooks
    prepend them), but we consider any other non-output item a mismatch.
    """

    outs = 0
    for it in items:
        if not isinstance(it, dict):
            return False
        if it.get("type") == "function_call_output":
            outs += 1
            continue
        if it.get("type") == "function_call":
            return False
        role = it.get("role")
        if role in {"system", "developer"}:
            continue
        # Unknown item (could be user/assistant/other Responses item) - don't
        # treat this as an output-only continuation.
        return False
    return outs > 0


def _prepend_function_calls_for_responses(tool_calls: Sequence[ToolCall], outputs: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    calls: list[Mapping[str, Any]] = []
    for tc in tool_calls:
        calls.append(
            {
                "type": "function_call",
                "call_id": tc.tool_use_id,
                "name": tc.name,
                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
            }
        )
    return calls + list(outputs)


@dataclass(frozen=True, slots=True)
class RunResult:
    final_text: str
    session_id: str
    events: Sequence[Any]


class AgentRuntime:
    def __init__(self, options: OpenAgenticOptions, *, agent_name: str | None = None, parent_tool_use_id: str | None = None):
        self._options = options
        self._agent_name = agent_name
        self._parent_tool_use_id = parent_tool_use_id

    def _with_base_system(self, items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        sys_prompt = getattr(self, "_base_system_prompt", None)
        sys_role = getattr(self, "_base_system_role", None) or "system"
        if not isinstance(sys_prompt, str) or not sys_prompt.strip():
            return items
        if items and isinstance(items[0], dict) and items[0].get("role") == sys_role:
            # The runtime keeps the base system prompt stable by rewriting index 0.
            return [{"role": sys_role, "content": sys_prompt}, *items[1:]]
        return [{"role": sys_role, "content": sys_prompt}, *items]

    def _rebuild_provider_input(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
        provider_protocol: str,
        options: OpenAgenticOptions,
    ) -> list[Mapping[str, Any]]:
        events = store.read_events(session_id)
        if provider_protocol == "legacy":
            items = list(
                rebuild_messages(
                    events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        else:
            items = list(
                rebuild_responses_input(
                    events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        return self._with_base_system(items)

    async def _maybe_prune_tool_outputs(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
    ) -> AsyncIterator[Any]:
        options = self._options
        if not getattr(options, "compaction", None) or not options.compaction.prune:
            return

        # Append-only marking of old tool results.
        events = store.read_events(session_id)
        to_prune = select_tool_outputs_to_prune(events=events, compaction=options.compaction)
        if not to_prune:
            return
        now = time.time()
        for tid in to_prune:
            ev = ToolOutputCompacted(
                tool_use_id=tid,
                compacted_ts=now,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, ev)
            yield ev

    async def _run_compaction_pass(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
        provider_protocol: str,
    ) -> AsyncIterator[Any]:
        """Run a dedicated, tool-less compaction call and store a summary pivot."""

        options = self._options

        complete_fn: Any = getattr(options.provider, "complete", None)
        if complete_fn is None:
            return

        # Summarize the current post-pivot window. Use rebuild_messages so the
        # compaction model sees a normal chat-style transcript.
        history = list(
            rebuild_messages(
                store.read_events(session_id),
                max_events=options.resume_max_events,
                max_bytes=options.resume_max_bytes,
            )
        )

        # OpenCode parity: allow plugins to inject compaction context/prompt.
        compacting = {"context": [], "prompt": None}
        out2, hook_events, decision = await options.hooks.run_session_compacting(
            output=compacting,
            context={"session_id": session_id, "agent_name": self._agent_name},
        )
        for he in hook_events:
            store.append_event(session_id, he)
            yield he
        if decision is not None and decision.block:
            return
        compacting2 = out2 if isinstance(out2, dict) else compacting
        ctx_items = compacting2.get("context") if isinstance(compacting2, dict) else None
        ctx_list = [str(x) for x in ctx_items] if isinstance(ctx_items, list) else []
        prompt_override = compacting2.get("prompt") if isinstance(compacting2, dict) else None
        if isinstance(prompt_override, str) and prompt_override.strip():
            prompt_text = prompt_override.strip()
        else:
            prompt_text = "\n\n".join([COMPACTION_USER_INSTRUCTION, *ctx_list]).strip()

        # The compaction marker question is already present in history (rebuild
        # renders UserCompaction as "What did we do so far?").
        compaction_input: list[Mapping[str, Any]] = [
            {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": prompt_text},
        ]

        if provider_protocol == "legacy":
            kwargs = {
                "model": options.model,
                "messages": compaction_input,
                "tools": (),
                "api_key": options.api_key,
            }
        else:
            kwargs = {
                "model": options.model,
                "input": compaction_input,
                "tools": (),
                "api_key": options.api_key,
                # Avoid polluting provider-side stored conversations.
                "store": False,
                "previous_response_id": None,
            }

        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
        summary = model_out.assistant_text or ""
        if not summary.strip():
            return

        msg = AssistantMessage(
            text=summary.strip(),
            is_summary=True,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, msg)
        yield msg

    def _expand_command_args(self, template: str, args: str) -> str:
        import re

        raw_args = args or ""

        # OpenCode tokenization: [Image N] is one token, quoted strings are one
        # token, otherwise split by whitespace.
        args_regex = re.compile(r'(?:\[Image\s+\d+\]|"[^"]*"|\'[^\']*\'|[^\s"\']+)', re.IGNORECASE)
        quote_trim = re.compile(r"^['\"]|['\"]$")

        raw = args_regex.findall(raw_args)
        parts = [quote_trim.sub("", x) for x in raw]

        placeholder_regex = re.compile(r"\$(\d+)")
        placeholders = placeholder_regex.findall(template)
        last = 0
        for s in placeholders:
            try:
                n = int(s)
            except Exception:  # noqa: BLE001
                continue
            if n > last:
                last = n

        def repl(m: re.Match[str]) -> str:
            try:
                position = int(m.group(1))
            except Exception:  # noqa: BLE001
                return ""
            arg_index = position - 1
            if arg_index >= len(parts) or arg_index < 0:
                return ""
            if position == last:
                return " ".join(parts[arg_index:])
            return parts[arg_index]

        with_args = placeholder_regex.sub(repl, template)
        uses_arguments_placeholder = "$ARGUMENTS" in template
        out = with_args.replace("$ARGUMENTS", raw_args)

        if not placeholders and not uses_arguments_placeholder and raw_args.strip():
            out = out + "\n\n" + raw_args

        return out

    async def _render_slash_command(
        self,
        *,
        session_id: str,
        tool_use_id: str,
        name: str,
        args: str,
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        """Render a slash command template with file/shell expansions.

        Returns (rendered_text, sources, parts).
        """

        options = self._options
        project_dir = options.project_dir or options.cwd
        tmpl = load_command_template(name=name, project_dir=str(project_dir))
        if tmpl is None:
            raise FileNotFoundError(f"SlashCommand: not found: {name}")

        is_subtask = bool(getattr(tmpl, "subtask", None) is True)

        text = self._expand_command_args(tmpl.content, args)

        sources = [tmpl.source]

        # Expand inline shell snippets: !`cmd`.
        import re as _re

        bash_regex = _re.compile(r"!`([^`]+)`")
        shell_matches = list(bash_regex.finditer(text))
        if shell_matches:
            if options.allowed_tools is not None and "Bash" not in set(options.allowed_tools):
                raise RuntimeError("SlashCommand: Bash tool is not allowed")

            approvals: list[tuple[str, dict[str, Any]]] = []
            for i, m in enumerate(shell_matches):
                cmd = (m.group(1) or "").strip()
                approval = await options.permission_gate.approve(
                    "Bash",
                    {"command": cmd, "workdir": options.cwd, "description": "SlashCommand shell"},
                    context={
                        "session_id": session_id,
                        "tool_use_id": f"{tool_use_id}:bash:{i}",
                        "agent_name": self._agent_name,
                    },
                )
                if not approval.allowed:
                    raise RuntimeError("SlashCommand: Bash not approved")
                approvals.append((cmd, dict(approval.updated_input or {"command": cmd, "workdir": options.cwd})))

            async def _run_bash(inp: dict[str, Any]) -> str:
                tool = options.tools.get("Bash")
                try:
                    out_obj = await tool.run(inp, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
                except Exception as e:  # noqa: BLE001
                    return f"Error executing command: {e}"
                if isinstance(out_obj, dict):
                    s = out_obj.get("stdout")
                    if isinstance(s, str):
                        return s
                return ""

            results = await asyncio.gather(*[_run_bash(inp) for _, inp in approvals])
            idx = 0

            def _sub(_: _re.Match[str]) -> str:
                nonlocal idx
                out = results[idx] if idx < len(results) else ""
                idx += 1
                return out

            text = bash_regex.sub(_sub, text)

        text = text.strip()

        # OpenCode resolvePromptParts(): keep structured parts (text + file:// + agent).
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if is_subtask:
            # Subtask commands only forward the prompt text (no file parts).
            agent_name = getattr(tmpl, "agent", None)
            if not isinstance(agent_name, str) or not agent_name:
                agent_name = name
            parts = [
                {
                    "type": "subtask",
                    "agent": agent_name,
                    "description": getattr(tmpl, "description", None) if isinstance(getattr(tmpl, "description", None), str) else "",
                    "command": name,
                    "prompt": text,
                    "model": getattr(tmpl, "model", None) if isinstance(getattr(tmpl, "model", None), str) else None,
                }
            ]

        refs = [m.group(1) for m in FILE_REGEX.finditer(text) if m.group(1)]
        refs = list(dict.fromkeys(refs))

        injections: list[str] = []

        def _find_worktree_root(start: Path) -> Path:
            cur = start.resolve()
            for p in [cur, *cur.parents]:
                if (p / ".git").exists():
                    return p
            return Path(cur.anchor or "/").resolve()

        worktree = _find_worktree_root(Path(options.project_dir or options.cwd).expanduser().resolve())
        for i, ref in enumerate(refs):
            if not isinstance(ref, str) or not ref:
                continue

            # @agent / @file (OpenCode resolves relative to worktree).
            ref_path = ref
            if ref_path.startswith("~/"):
                home = Path(os.environ.get("OPENCODE_TEST_HOME") or Path.home()).expanduser().resolve()
                ref_path = str(home / ref_path[2:])
            p = Path(ref_path)
            if not p.is_absolute():
                p = worktree / p
            p = p.expanduser().resolve()

            if not p.exists():
                if ref in (options.agents or {}):
                    if not is_subtask:
                        parts.append({"type": "agent", "name": ref})
                continue

            if not is_subtask:
                parts.append(
                    {
                        "type": "file",
                        "url": p.as_uri(),
                        "filename": ref,
                        "mime": "application/x-directory" if p.is_dir() else "text/plain",
                    }
                )

            if is_subtask:
                continue

            if p.is_dir():
                if options.allowed_tools is not None and "List" not in set(options.allowed_tools):
                    raise RuntimeError("SlashCommand: List tool is not allowed")
                approval = await options.permission_gate.approve(
                    "List",
                    {"path": str(p)},
                    context={"session_id": session_id, "tool_use_id": f"{tool_use_id}:list:{i}", "agent_name": self._agent_name},
                )
                if not approval.allowed:
                    raise RuntimeError("SlashCommand: List not approved")
                tool = options.tools.get("List")
                out_obj = await tool.run(approval.updated_input or {"path": str(p)}, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
                out = out_obj.get("output") if isinstance(out_obj, dict) else None
                if isinstance(out, str) and out:
                    injections.append(out)
                continue

            # Default: treat as text/plain and inline via Read tool.
            if options.allowed_tools is not None and "Read" not in set(options.allowed_tools):
                raise RuntimeError("SlashCommand: Read tool is not allowed")
            approval = await options.permission_gate.approve(
                "Read",
                {"file_path": str(p)},
                context={"session_id": session_id, "tool_use_id": f"{tool_use_id}:read:{i}", "agent_name": self._agent_name},
            )
            if not approval.allowed:
                raise RuntimeError("SlashCommand: Read not approved")
            tool = options.tools.get("Read")
            out_obj = await tool.run(approval.updated_input or {"file_path": str(p)}, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
            content = out_obj.get("content") if isinstance(out_obj, dict) else None
            if isinstance(content, str) and content:
                injections.append(content)

        rendered = text
        if injections and not is_subtask:
            rendered = (rendered + "\n\n" + "\n\n".join([b for b in injections if b.strip()])).strip()
        return rendered, sources, parts

    async def query(self, prompt: str) -> AsyncIterator[Any]:
        options = self._options

        mcp_clients: list[StdioMcpClient] = []
        remote_mcp_clients: list[RemoteMcpClient] = []
        try:
            # MCP (parity): register SDK and local-stdio MCP tools.
            if options.mcp_servers:
                for server_key, cfg in options.mcp_servers.items():
                    if isinstance(cfg, McpSdkServerConfig) and cfg.type == "sdk":
                        for wrapper in wrap_sdk_server_tools(server_key, cfg):
                            try:
                                options.tools.get(wrapper.name)
                            except KeyError:
                                options.tools.register(wrapper)
                        continue

                    if isinstance(cfg, dict) and cfg.get("type") == "local":
                        cmd = cfg.get("command")
                        env = cfg.get("environment") if isinstance(cfg.get("environment"), dict) else None
                        if not isinstance(cmd, list) or not all(isinstance(x, str) and x for x in cmd):
                            continue
                        client = StdioMcpClient(command=list(cmd), environment=env, cwd=options.cwd)
                        try:
                            await client.start()
                            tools = await client.list_tools()
                        except Exception:
                            # Non-fatal: allow sessions to run even if an MCP server is down.
                            try:
                                await client.close()
                            except Exception:
                                pass
                            continue

                        for w in wrap_stdio_mcp_tools(str(server_key), client=client, tools=tools):
                            try:
                                options.tools.get(w.name)
                            except KeyError:
                                options.tools.register(w)

                        # Prompts/resources are part of the MCP surface too.
                        try:
                            prompts = await client.list_prompts()
                            for w in wrap_stdio_mcp_prompts(str(server_key), client=client, prompts=prompts):
                                try:
                                    options.tools.get(w.name)
                                except KeyError:
                                    options.tools.register(w)
                        except Exception:
                            pass

                        try:
                            resources = await client.list_resources()
                            for w in wrap_stdio_mcp_resources(str(server_key), client=client, resources=resources):
                                try:
                                    options.tools.get(w.name)
                                except KeyError:
                                    options.tools.register(w)
                        except Exception:
                            pass
                        mcp_clients.append(client)

                    if isinstance(cfg, dict) and cfg.get("type") == "remote":
                        url = cfg.get("url")
                        if not isinstance(url, str) or not url:
                            continue
                        headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else None
                        client2 = RemoteMcpClient(
                            url=url,
                            headers={str(k): str(v) for k, v in (headers or {}).items()},
                            server_key=str(server_key),
                        )
                        try:
                            tools2 = await client2.list_tools()
                        except Exception:
                            try:
                                await client2.close()
                            except Exception:
                                pass
                            continue

                        for w in wrap_http_mcp_tools(str(server_key), client=client2, tools=tools2):
                            try:
                                options.tools.get(w.name)
                            except KeyError:
                                options.tools.register(w)

                        try:
                            for w in wrap_http_mcp_prompts(str(server_key), client=client2, prompts=await client2.list_prompts()):
                                try:
                                    options.tools.get(w.name)
                                except KeyError:
                                    options.tools.register(w)
                        except Exception:
                            pass

                        try:
                            for w in wrap_http_mcp_resources(
                                str(server_key), client=client2, resources=await client2.list_resources()
                            ):
                                try:
                                    options.tools.get(w.name)
                                except KeyError:
                                    options.tools.register(w)
                        except Exception:
                            pass

                        remote_mcp_clients.append(client2)

            # Expose Task only when agents are configured.
            if options.agents:
                try:
                    options.tools.get("Task")
                except KeyError:
                    options.tools.register(TaskTool())

            store = options.session_store
            if store is None:
                root = options.session_root or _default_session_root()
                store = FileSessionStore(root_dir=root)

            previous_response_id: str | None = None
            supports_previous_response_id = True
            pending_responses_tool_calls: list[ToolCall] = []
            pending_responses_history: list[Mapping[str, Any]] = []
            resume_protocol: str | None = None

            if options.resume:
                session_id = options.resume
                past_events = store.read_events(session_id)
                for e in reversed(past_events):
                    if isinstance(e, Result) and isinstance(getattr(e, "provider_metadata", None), dict):
                        pm = e.provider_metadata or {}
                        proto = pm.get("protocol")
                        if isinstance(proto, str) and proto:
                            resume_protocol = proto
                        spri = pm.get("supports_previous_response_id")
                        if isinstance(spri, bool):
                            supports_previous_response_id = spri
                        break
                for e in reversed(past_events):
                    if isinstance(e, Result) and isinstance(getattr(e, "response_id", None), str) and e.response_id:
                        previous_response_id = e.response_id
                        break
                if resume_protocol == "responses" and supports_previous_response_id is False:
                    messages = list(
                        rebuild_responses_input(
                            past_events,
                            max_events=options.resume_max_events,
                            max_bytes=options.resume_max_bytes,
                        )
                    )
                else:
                    messages = list(
                        rebuild_messages(
                            past_events,
                            max_events=options.resume_max_events,
                            max_bytes=options.resume_max_bytes,
                        )
                    )
            else:
                metadata: dict[str, Any] = {
                    "cwd": options.cwd,
                    "provider_name": getattr(options.provider, "name", "unknown"),
                    "model": options.model,
                }
                if options.setting_sources:
                    metadata["setting_sources"] = list(options.setting_sources)
                if options.allowed_tools is not None:
                    metadata["allowed_tools"] = list(options.allowed_tools)
                session_id = store.create_session(metadata=metadata)
                messages = []

            init = SystemInit(
                session_id=session_id,
                cwd=options.cwd,
                sdk_version=_SDK_VERSION,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
                enabled_tools=options.tools.names(),
                enabled_providers=[getattr(options.provider, "name", "unknown")],
            )
            store.append_event(session_id, init)
            yield init

            for he in await options.hooks.run_session_start(context={"session_id": session_id, "agent_name": self._agent_name}):
                store.append_event(session_id, he)
                yield he

            provider_protocol: str = resume_protocol or _detect_provider_protocol(options.provider)

            built = _build_project_system_prompt(options)
            sys_prompt = built.system_text
            sys_role = _base_system_role_for_model(model_id=options.model, provider_protocol=provider_protocol)
            if built.is_codex_session:
                sys_role = "user"
            if sys_prompt:
                messages.insert(0, {"role": sys_role, "content": sys_prompt})
            self._base_system_prompt = sys_prompt
            self._base_system_role = sys_role if sys_prompt else None
            self._base_instructions = built.instructions

            prompt2, hook_events0, decision0 = await options.hooks.run_user_prompt_submit(
                prompt=prompt,
                context={"session_id": session_id, "agent_name": self._agent_name},
            )
            for he in hook_events0:
                store.append_event(session_id, he)
                yield he
            if decision0 is not None and decision0.block:
                for he in await options.hooks.run_session_end(context={"session_id": session_id, "agent_name": self._agent_name}):
                    store.append_event(session_id, he)
                    yield he
                final = Result(
                    final_text="",
                    session_id=session_id,
                    stop_reason=f"blocked:user_prompt_submit:{decision0.block_reason or 'blocked'}",
                    steps=0,
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )
                store.append_event(session_id, final)
                yield final
                return

            prompt3 = _maybe_expand_execute_skill_prompt(prompt2, options)
            prompt3 = _maybe_expand_list_skills_prompt(prompt3, options)

            # OpenCode-style direct slash command execution: if the user typed
            # `/name ...` and the command exists, expand it before sending to the
            # model (no tool call required).
            if isinstance(prompt3, str) and prompt3.lstrip().startswith("/"):
                s = prompt3.lstrip()
                # Only consider the first line for command parsing; remaining
                # lines are preserved as part of the args.
                first, *rest = s.splitlines()
                first = first.strip()
                if first.startswith("/") and len(first) > 1:
                    parts = first[1:].split(None, 1)
                    cmd_name = parts[0].strip() if parts else ""
                    cmd_args = (parts[1] if len(parts) > 1 else "")
                    if rest:
                        cmd_args = (cmd_args + "\n" + "\n".join(rest)).strip()

                    if cmd_name:
                        try:
                            project_dir = options.project_dir or options.cwd
                            if load_command_template(name=cmd_name, project_dir=str(project_dir)) is not None:
                                rendered, _, _ = await self._render_slash_command(
                                    session_id=session_id,
                                    tool_use_id=f"usercmd:{uuid.uuid4().hex}",
                                    name=cmd_name,
                                    args=cmd_args,
                                )
                                prompt3 = rendered
                        except Exception:  # noqa: BLE001
                            # Fall back to raw prompt if expansion fails.
                            pass

            store.append_event(
                session_id,
                UserMessage(
                    text=prompt3,
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                ),
            )
            messages.append({"role": "user", "content": prompt3})

            # provider_protocol is computed before first system prompt injection.
            steps = 0
            while steps < options.max_steps:
                if options.abort_event is not None and getattr(options.abort_event, "is_set", lambda: False)():
                    for he in await options.hooks.run_session_end(
                        context={"session_id": session_id, "agent_name": self._agent_name}
                    ):
                        store.append_event(session_id, he)
                        yield he
                    final = Result(
                        final_text="",
                        session_id=session_id,
                        stop_reason="interrupted",
                        steps=steps,
                        parent_tool_use_id=self._parent_tool_use_id,
                        agent_name=self._agent_name,
                    )
                    store.append_event(session_id, final)
                    yield final
                    return

                steps += 1
                tool_names = options.tools.names()
                if options.agents and "Task" not in set(tool_names):
                    tool_names = [*tool_names, "Task"]
                if options.allowed_tools is not None:
                    allowed = set(options.allowed_tools)
                    tool_names = [t for t in tool_names if t in allowed]

                tool_schemas: Sequence[Mapping[str, Any]] = ()
                if provider_protocol == "legacy":
                    tool_schemas = tool_schemas_for_openai(
                        tool_names,
                        registry=options.tools,
                        context={"cwd": options.cwd, "project_dir": options.project_dir},
                    )
                else:
                    tool_schemas = tool_schemas_for_responses(
                        tool_names,
                        registry=options.tools,
                        context={"cwd": options.cwd, "project_dir": options.project_dir},
                    )

                # Soft compaction (tool-output pruning) is only meaningful when we
                # send full history (legacy or Responses fallback mode).
                if provider_protocol == "legacy" or not supports_previous_response_id:
                    async for ev in self._maybe_prune_tool_outputs(store=store, session_id=session_id):
                        yield ev
                    messages = self._rebuild_provider_input(
                        store=store,
                        session_id=session_id,
                        provider_protocol=provider_protocol,
                        options=options,
                    )

                base_role = getattr(self, "_base_system_role", None) or "system"
                if getattr(self, "_base_system_prompt", None) and messages and messages[0].get("role") == base_role:
                    messages[0] = {
                        "role": base_role,
                        "content": self._base_system_prompt,  # type: ignore[arg-type]
                    }

                model_ctx = {
                    "session_id": session_id,
                    "model": options.model,
                    "provider_name": getattr(options.provider, "name", "unknown"),
                    "agent_name": self._agent_name,
                }
                messages2, hook_events, decision = await options.hooks.run_before_model_call(messages=messages, context=model_ctx)
                for he in hook_events:
                    store.append_event(session_id, he)
                    yield he
                if decision is not None and decision.block:
                    for he in await options.hooks.run_session_end(context=model_ctx):
                        store.append_event(session_id, he)
                        yield he
                    final = Result(
                        final_text="",
                        session_id=session_id,
                        stop_reason=f"blocked:before_model_call:{decision.block_reason or 'blocked'}",
                        steps=steps,
                        parent_tool_use_id=self._parent_tool_use_id,
                        agent_name=self._agent_name,
                    )
                    store.append_event(session_id, final)
                    yield final
                    return
                messages = list(messages2)

                model_out: ModelOutput
                if hasattr(options.provider, "stream"):
                    stream_fn: Any = getattr(options.provider, "stream")
                    interrupted = False
                    parts: list[str] = []
                    tool_calls: list[ToolCall] = []
                    stream_response_id: str | None = None
                    stream_usage: Mapping[str, Any] | None = None

                    for attempt in range(2):
                        parts = []
                        tool_calls = []
                        stream_response_id = None
                        stream_usage = None

                        if provider_protocol == "legacy":
                            kwargs = {"model": options.model, "messages": messages, "tools": tool_schemas, "api_key": options.api_key}
                            stream_iter = stream_fn(**_filter_supported_kwargs(stream_fn, kwargs))
                        else:
                            can_thread = supports_previous_response_id and _callable_accepts_kw(stream_fn, "previous_response_id")
                            prev_id = previous_response_id if can_thread else None
                            instructions = getattr(self, "_base_instructions", None)
                            kwargs = {
                                "model": options.model,
                                "input": messages,
                                "tools": tool_schemas,
                                "api_key": options.api_key,
                                "previous_response_id": prev_id,
                                "store": True,
                                "instructions": instructions,
                            }
                            stream_iter = stream_fn(**_filter_supported_kwargs(stream_fn, kwargs))

                        try:
                            async for ev in stream_iter:
                                if options.abort_event is not None and getattr(options.abort_event, "is_set", lambda: False)():
                                    interrupted = True
                                    break
                                ev_type = getattr(ev, "type", None)
                                if ev_type is None and isinstance(ev, dict):
                                    ev_type = ev.get("type")
                                if ev_type == "text_delta":
                                    delta = getattr(ev, "delta", None)
                                    if delta is None and isinstance(ev, dict):
                                        delta = ev.get("delta")
                                    if isinstance(delta, str) and delta:
                                        parts.append(delta)
                                        de = AssistantDelta(text_delta=delta, parent_tool_use_id=self._parent_tool_use_id, agent_name=self._agent_name)
                                        store.append_event(session_id, de)
                                        yield de
                                elif ev_type == "tool_call":
                                    tc = getattr(ev, "tool_call", None)
                                    if tc is None and isinstance(ev, dict):
                                        tc = ev.get("tool_call")
                                    if isinstance(tc, ToolCall):
                                        tool_calls.append(tc)
                                elif ev_type == "done":
                                    rid = getattr(ev, "response_id", None)
                                    if rid is None and isinstance(ev, dict):
                                        rid = ev.get("response_id")
                                    if isinstance(rid, str) and rid:
                                        stream_response_id = rid
                                    u = getattr(ev, "usage", None)
                                    if u is None and isinstance(ev, dict):
                                        u = ev.get("usage")
                                    if isinstance(u, dict):
                                        stream_usage = u
                                    break
                        except RuntimeError as e:
                            can_retry_prev = supports_previous_response_id and previous_response_id is not None and _unsupported_previous_response_id_error(e)
                            can_retry_link = supports_previous_response_id and _no_tool_call_found_for_call_output_error(e)
                            can_retry = (
                                provider_protocol != "legacy"
                                and attempt == 0
                                and supports_previous_response_id
                                and not parts
                                and not tool_calls
                                and stream_response_id is None
                                and (can_retry_prev or can_retry_link)
                            )
                            if can_retry:
                                supports_previous_response_id = False
                                if pending_responses_tool_calls and pending_responses_history and _looks_like_outputs_without_calls(messages):
                                    outs = _extract_function_call_outputs(messages)
                                    messages = [
                                        *list(pending_responses_history),
                                        *_prepend_function_calls_for_responses(pending_responses_tool_calls, outs),
                                    ]
                                continue
                            raise
                        break

                    if interrupted:
                        for he in await options.hooks.run_session_end(context=model_ctx):
                            store.append_event(session_id, he)
                            yield he
                        final = Result(
                            final_text="",
                            session_id=session_id,
                            stop_reason="interrupted",
                            steps=steps,
                            parent_tool_use_id=self._parent_tool_use_id,
                            agent_name=self._agent_name,
                        )
                        store.append_event(session_id, final)
                        yield final
                        return

                    assistant_text = "".join(parts) if parts else None
                    model_out = ModelOutput(assistant_text=assistant_text, tool_calls=tool_calls, usage=stream_usage, response_id=stream_response_id)
                else:
                    complete_fn: Any = getattr(options.provider, "complete")
                    if provider_protocol == "legacy":
                        kwargs = {"model": options.model, "messages": messages, "tools": tool_schemas, "api_key": options.api_key}
                        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
                    else:
                        prev_id = previous_response_id if supports_previous_response_id else None
                        instructions = getattr(self, "_base_instructions", None)
                        try:
                            kwargs = {
                                "model": options.model,
                                "input": messages,
                                "tools": tool_schemas,
                                "api_key": options.api_key,
                                "previous_response_id": prev_id,
                                "store": True,
                                "instructions": instructions,
                            }
                            model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
                        except RuntimeError as e:
                            can_retry_prev = supports_previous_response_id and previous_response_id is not None and _unsupported_previous_response_id_error(e)
                            can_retry_link = supports_previous_response_id and _no_tool_call_found_for_call_output_error(e)
                            can_retry = can_retry_prev or can_retry_link
                            if not can_retry:
                                raise
                            supports_previous_response_id = False
                            if pending_responses_tool_calls and pending_responses_history and _looks_like_outputs_without_calls(messages):
                                outs = _extract_function_call_outputs(messages)
                                messages = [
                                    *list(pending_responses_history),
                                    *_prepend_function_calls_for_responses(pending_responses_tool_calls, outs),
                                ]
                            kwargs = {
                                "model": options.model,
                                "input": messages,
                                "tools": tool_schemas,
                                "api_key": options.api_key,
                                "previous_response_id": None,
                                "store": True,
                                "instructions": instructions,
                            }
                            model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))

                model_out2, hook_events2, decision2 = await options.hooks.run_after_model_call(output=model_out, context=model_ctx)
                for he in hook_events2:
                    store.append_event(session_id, he)
                    yield he
                if decision2 is not None and decision2.block:
                    for he in await options.hooks.run_session_end(context=model_ctx):
                        store.append_event(session_id, he)
                        yield he
                    final = Result(
                        final_text="",
                        session_id=session_id,
                        stop_reason=f"blocked:after_model_call:{decision2.block_reason or 'blocked'}",
                        steps=steps,
                        parent_tool_use_id=self._parent_tool_use_id,
                        agent_name=self._agent_name,
                    )
                    store.append_event(session_id, final)
                    yield final
                    return
                model_out = model_out2

                if model_out.tool_calls:
                    tool_calls = list(model_out.tool_calls)
                    pending_responses_tool_calls = tool_calls
                    if provider_protocol == "legacy":
                        messages.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": tc.tool_use_id,
                                        "type": "function",
                                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                                    }
                                    for tc in tool_calls
                                ],
                            }
                        )
                        for tc in tool_calls:
                            async for e in self._run_tool_call(session_id=session_id, tool_call=tc, store=store, hooks=options.hooks):
                                yield e
                                if isinstance(e, ToolResult):
                                    messages.append(
                                        {
                                            "role": "tool",
                                            "tool_call_id": tc.tool_use_id,
                                            "content": json.dumps(_tool_result_payload(e), ensure_ascii=False),
                                        }
                                    )
                        continue

                    if supports_previous_response_id:
                        tool_output_items: list[Mapping[str, Any]] = []
                        for tc in tool_calls:
                            async for e in self._run_tool_call(session_id=session_id, tool_call=tc, store=store, hooks=options.hooks):
                                yield e
                                if isinstance(e, ToolResult):
                                    tool_output_items.append(
                                        {
                                            "type": "function_call_output",
                                            "call_id": tc.tool_use_id,
                                            "output": json.dumps(_tool_result_payload(e), ensure_ascii=False),
                                        }
                                    )
                        if model_out.response_id:
                            previous_response_id = model_out.response_id
                        pending_responses_history = list(messages)
                        messages = tool_output_items
                        continue

                    for tc in tool_calls:
                        messages.append({"type": "function_call", "call_id": tc.tool_use_id, "name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)})
                        async for e in self._run_tool_call(session_id=session_id, tool_call=tc, store=store, hooks=options.hooks):
                            yield e
                            if isinstance(e, ToolResult):
                                messages.append(
                                    {
                                        "type": "function_call_output",
                                        "call_id": tc.tool_use_id,
                                        "output": json.dumps(_tool_result_payload(e), ensure_ascii=False),
                                    }
                                )
                    continue

                if model_out.assistant_text is None:
                    for he in await options.hooks.run_session_end(context=model_ctx):
                        store.append_event(session_id, he)
                        yield he
                    final = Result(
                        final_text="",
                        session_id=session_id,
                        stop_reason="no_output",
                        steps=steps,
                        parent_tool_use_id=self._parent_tool_use_id,
                        agent_name=self._agent_name,
                    )
                    store.append_event(session_id, final)
                    yield final
                    return

                msg = AssistantMessage(text=model_out.assistant_text, parent_tool_use_id=self._parent_tool_use_id, agent_name=self._agent_name)
                store.append_event(session_id, msg)
                yield msg

                if options.compaction.auto and (provider_protocol == "legacy" or not supports_previous_response_id):
                    if would_overflow(compaction=options.compaction, usage=model_out.usage if isinstance(model_out.usage, dict) else None):
                        marker = UserCompaction(auto=True, reason="overflow", parent_tool_use_id=self._parent_tool_use_id, agent_name=self._agent_name)
                        store.append_event(session_id, marker)
                        yield marker
                        async for ev in self._run_compaction_pass(store=store, session_id=session_id, provider_protocol=provider_protocol):
                            yield ev
                        messages = self._rebuild_provider_input(store=store, session_id=session_id, provider_protocol=provider_protocol, options=options)
                        previous_response_id = None
                        cont = "Continue if you have next steps"
                        store.append_event(session_id, UserMessage(text=cont, parent_tool_use_id=self._parent_tool_use_id, agent_name=self._agent_name))
                        messages.append({"role": "user", "content": cont})
                        continue

                for he in await options.hooks.run_stop(final_text=model_out.assistant_text, context=model_ctx):
                    store.append_event(session_id, he)
                    yield he
                for he in await options.hooks.run_session_end(context=model_ctx):
                    store.append_event(session_id, he)
                    yield he

                final = Result(
                    final_text=model_out.assistant_text,
                    session_id=session_id,
                    stop_reason="end",
                    usage=model_out.usage if isinstance(model_out.usage, dict) else None,
                    response_id=model_out.response_id or previous_response_id,
                    provider_metadata={
                        **({"protocol": provider_protocol} if provider_protocol else {}),
                        **({"supports_previous_response_id": supports_previous_response_id} if provider_protocol == "responses" else {}),
                        **(dict(model_out.provider_metadata) if isinstance(model_out.provider_metadata, dict) else {}),
                    }
                    or None,
                    steps=steps,
                    parent_tool_use_id=self._parent_tool_use_id,
                    agent_name=self._agent_name,
                )
                store.append_event(session_id, final)
                yield final
                return

            final = Result(
                final_text="",
                session_id=session_id,
                stop_reason="max_steps",
                steps=steps,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            for he in await options.hooks.run_session_end(context={"session_id": session_id, "agent_name": self._agent_name}):
                store.append_event(session_id, he)
                yield he
            store.append_event(session_id, final)
            yield final
        finally:
            for c in mcp_clients:
                try:
                    await c.close()
                except Exception:  # noqa: BLE001
                    pass
            for c in remote_mcp_clients:
                try:
                    await c.close()
                except Exception:  # noqa: BLE001
                    pass

    async def _handle_ask_user_question(
        self,
        *,
        session_id: str,
        tool_call: ToolCall,
        tool_input: Mapping[str, Any],
        store: FileSessionStore,
    ) -> AsyncIterator[Any]:
        options = self._options

        questions = tool_input.get("questions")
        if isinstance(questions, dict):
            questions = [questions]

        if not isinstance(questions, list) or not questions:
            q_text0 = tool_input.get("question", tool_input.get("prompt"))
            if isinstance(q_text0, str) and q_text0.strip():
                opts0 = tool_input.get("options", tool_input.get("choices")) or []
                options0: list[dict[str, str]] = []
                if isinstance(opts0, list):
                    for opt in opts0:
                        if isinstance(opt, str) and opt.strip():
                            options0.append({"label": opt.strip()})
                            continue
                        if isinstance(opt, dict):
                            lab = opt.get("label", opt.get("name", opt.get("value")))
                            if isinstance(lab, str) and lab.strip():
                                options0.append({"label": lab.strip()})
                questions = [{"question": q_text0.strip(), "options": options0}]

        if not isinstance(questions, list) or not questions:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="InvalidAskUserQuestionInput",
                error_message="AskUserQuestion: 'questions' must be a non-empty list",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        user_answerer = options.permission_gate.user_answerer
        if user_answerer is None:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="NoUserAnswerer",
                error_message="AskUserQuestion: no user_answerer is configured",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        answers: dict[str, str] = {}
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                continue
            q_text = q.get("question")
            if not isinstance(q_text, str) or not q_text:
                continue
            opts = q.get("options") or []
            labels: list[str] = []
            if isinstance(opts, list):
                for opt in opts:
                    if isinstance(opt, dict):
                        lab = opt.get("label")
                        if isinstance(lab, str) and lab:
                            labels.append(lab)
            if not labels:
                labels = ["ok"]

            uq = UserQuestion(
                question_id=f"{tool_call.tool_use_id}:{i}",
                prompt=q_text,
                choices=labels,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, uq)
            yield uq
            ans = await user_answerer(uq)
            answers[q_text] = str(ans)

        result = ToolResult(
            tool_use_id=tool_call.tool_use_id,
            output={"questions": questions, "answers": answers},
            is_error=False,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, result)
        yield result

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

    async def _handle_todowrite(
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

        try:
            tool = options.tools.get(tool_name)
            output = await tool.run(tool_input, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
            todos = tool_input.get("todos")
            if isinstance(todos, list):
                # Persist a canonical OpenCode-like todo list.
                from .sessions.todos import normalize_todos_for_api

                normalized = normalize_todos_for_api(todos)
                p = store.session_dir(session_id) / "todos.json"
                p.write_text(json.dumps({"todos": normalized}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
