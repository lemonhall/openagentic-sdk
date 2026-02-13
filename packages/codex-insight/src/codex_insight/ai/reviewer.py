from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..config import InsightConfig
from ..parser.turns import Turn


@dataclass(frozen=True, slots=True)
class ReviewResult:
    markdown: str
    model: str
    generated_at: int


def _default_session_root() -> Path:
    return Path.home() / ".codex-insight" / "oa_sessions"

def _ensure_openagentic_sdk_importable() -> None:
    try:
        import openagentic_sdk  # noqa: F401

        return
    except Exception:  # noqa: BLE001
        pass

    # Dev fallback: when running inside the `openagentic-sdk` repo, make the
    # repo root importable so we can import `openagentic_sdk` without an extra
    # installation step.
    import sys

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "openagentic_sdk").is_dir():
            sys.path.insert(0, str(parent))
            break


def _build_prompt(*, messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    lines.append("你是一个严格、具体、可操作的对话审阅员。")
    lines.append("请对下面这段人类与 AI 的对话进行 Review，并用 Markdown 输出，包含：")
    lines.append("- 摘要（3-5 句）")
    lines.append("- 关键决策点（条目）")
    lines.append("- 问题与风险（指出具体轮次/片段）")
    lines.append("- 效率评估（是否有不必要往返）")
    lines.append("- 改进建议（可执行）")
    lines.append("")
    lines.append("对话：")
    for i, m in enumerate(messages, start=1):
        role = (m.get("role") or "?").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{i}. [{role}] {content}")
    return "\n".join(lines).strip() + "\n"


def _build_turns_prompt(*, scope: str, turns: list[Turn]) -> str:
    return _build_turns_prompt_with_trace(scope=scope, turns=turns, session_context=None, tool_traces=None)


def _build_turns_prompt_with_trace(
    *,
    scope: str,
    turns: list[Turn],
    session_context: list[tuple[str, str]] | None,
    tool_traces: dict[int, list[str]] | None,
) -> str:
    if scope == "turn":
        title = "单回合（turn）Review"
    elif scope == "selection":
        title = "多回合（selection）Review"
    else:
        title = "整段会话（session）Review"

    lines: list[str] = []
    lines.append("你是一个严格、具体、可操作的对话审阅员。")
    lines.append(f"目标：{title}。")
    lines.append("请重点审阅 assistant 的最终回复质量（正确性、可执行性、是否跑偏、是否浪费回合）。")
    lines.append("你的主要任务是：从“可见信息”（消息与 tool trace）还原 assistant 的执行过程，并诊断是否走偏。")
    lines.append("注意：你看不到 assistant 的隐藏思考/链路，请不要臆测；只能基于可见内容做推断，并标注推断依据。")
    lines.append("必要时参考 user 的输入；工具调用/输出仅作为背景证据，不要喧宾夺主。")
    lines.append("")
    lines.append("输出要求（Markdown）：")
    lines.append("- 摘要（3-5 句）")
    lines.append("- 逐回合点评（按 turn 编号列出）")
    lines.append("- 问题与风险（指向具体 turn 编号与片段）")
    lines.append("- 执行过程与走偏诊断（基于可见证据：目标→计划→动作→结果）")
    lines.append("- 可复用 workflow / checklist（能复用的步骤化流程，尽量通用）")
    lines.append("- 可沉淀到 AGENTS.md 的规则建议（最多 5 条，写成“必须/禁止/推荐”的规范语句）")
    lines.append("- 改进建议（可执行，下一次如何更快/更稳）")
    lines.append("")
    if session_context:
        lines.append("会话上下文（可能已脱敏/截断；仅供约束参考）：")
        for role, content in session_context:
            if not content.strip():
                continue
            lines.append(f"- [{role}] {content}")
        lines.append("")

    if tool_traces is not None:
        lines.append("说明：每个 turn 附带 tool trace（可能已脱敏/截断）。")
        lines.append("")

    lines.append("数据（turn 列表；包含 user 输入 + assistant 最终回复；并可能附带 tool trace）：")
    for t in turns:
        u = (t.user_text or "").strip()
        a = (t.assistant_text or "").strip()
        lines.append(f"Turn {t.index}:")
        lines.append(f"- User: {u}")
        lines.append(f"- Assistant(final): {a or '(empty)'}")
        if tool_traces is not None:
            trace = tool_traces.get(t.index) or []
            if trace:
                lines.append("- Tools:")
                for item in trace:
                    lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def review_messages(*, cfg: InsightConfig, messages: list[dict[str, str]]) -> ReviewResult:
    _ensure_openagentic_sdk_importable()
    try:
        from openagentic_sdk import OpenAgenticOptions, run
        from openagentic_sdk.permissions.gate import PermissionGate
        from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
        from openagentic_sdk.tools.registry import ToolRegistry
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "AI Review 需要 openagentic-sdk。\n"
            "如果你在 `packages/codex-insight` 的虚拟环境里运行，请执行：\n"
            "  uv pip install -p .\\.venv\\Scripts\\python.exe -e ..\\..\n"
        ) from e

    api_key = (cfg.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "未发现 API Key：请设置 RIGHTCODE_API_KEY / OPENAI_API_KEY，或在 `~/.codex-insight/config.toml` 配置 [ai].api_key。"
        )

    provider = OpenAIResponsesProvider(base_url=cfg.ai_base_url)
    prompt = _build_prompt(messages=messages)
    now = int(time.time())

    options = OpenAgenticOptions(
        provider=provider,
        model=cfg.ai_review_model,
        api_key=api_key,
        cwd=str(Path.cwd()),
        max_steps=8,
        permission_gate=PermissionGate(permission_mode="deny"),
        tools=ToolRegistry(),
        allowed_tools=[],
        session_root=_default_session_root(),
    )
    rr = await run(prompt=prompt, options=options)
    text = (rr.final_text or "").strip() or "(empty)"
    return ReviewResult(markdown=text, model=cfg.ai_review_model, generated_at=now)


async def review_turns(*, cfg: InsightConfig, scope: str, turns: list[Turn]) -> ReviewResult:
    _ensure_openagentic_sdk_importable()
    try:
        from openagentic_sdk import OpenAgenticOptions, run
        from openagentic_sdk.permissions.gate import PermissionGate
        from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
        from openagentic_sdk.tools.registry import ToolRegistry
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "AI Review 需要 openagentic-sdk。\n"
            "如果你在 `packages/codex-insight` 的虚拟环境里运行，请执行：\n"
            "  uv pip install -p .\\.venv\\Scripts\\python.exe -e ..\\..\n"
        ) from e

    api_key = (cfg.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "未发现 API Key：请设置 RIGHTCODE_API_KEY / OPENAI_API_KEY，或在 `~/.codex-insight/config.toml` 配置 [ai].api_key。"
        )

    prompt = _build_turns_prompt(scope=scope, turns=turns)
    now = int(time.time())

    provider = OpenAIResponsesProvider(base_url=cfg.ai_base_url)
    options = OpenAgenticOptions(
        provider=provider,
        model=cfg.ai_review_model,
        api_key=api_key,
        cwd=str(Path.cwd()),
        max_steps=8,
        permission_gate=PermissionGate(permission_mode="deny"),
        tools=ToolRegistry(),
        allowed_tools=[],
        session_root=_default_session_root(),
    )
    rr = await run(prompt=prompt, options=options)
    text = (rr.final_text or "").strip() or "(empty)"
    return ReviewResult(markdown=text, model=cfg.ai_review_model, generated_at=now)


async def review_turns_stream(
    *,
    cfg: InsightConfig,
    scope: str,
    turns: list[Turn],
    rollout_path: str | None = None,
    include_context_user_messages: bool = False,
    on_delta: Callable[[str], None] | None = None,
    abort_event: Any | None = None,
) -> ReviewResult:
    """Stream a review.

    - `on_delta` receives assistant text deltas (may be called frequently).
    - `abort_event` should have an `is_set()` method (e.g. `threading.Event`).
    """
    _ensure_openagentic_sdk_importable()
    try:
        from openagentic_sdk import OpenAgenticOptions, query
        from openagentic_sdk.events import AssistantDelta, Result
        from openagentic_sdk.permissions.gate import PermissionGate
        from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
        from openagentic_sdk.tools.registry import ToolRegistry
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "AI Review 需要 openagentic-sdk。\n"
            "如果你在 `packages/codex-insight` 的虚拟环境里运行，请执行：\n"
            "  uv pip install -p .\\.venv\\Scripts\\python.exe -e ..\\..\n"
        ) from e

    api_key = (cfg.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "未发现 API Key：请设置 RIGHTCODE_API_KEY / OPENAI_API_KEY，或在 `~/.codex-insight/config.toml` 配置 [ai].api_key。"
        )

    session_context: list[tuple[str, str]] | None = None
    tool_traces: dict[int, list[str]] | None = None
    if rollout_path:
        session_context, tool_traces = _extract_context_and_tool_traces(
            rollout_path,
            include_context_user_messages=include_context_user_messages,
        )
    prompt = _build_turns_prompt_with_trace(
        scope=scope,
        turns=turns,
        session_context=session_context,
        tool_traces=tool_traces,
    )
    now = int(time.time())

    provider = OpenAIResponsesProvider(base_url=cfg.ai_base_url, timeout_s=120.0)
    options = OpenAgenticOptions(
        provider=provider,
        model=cfg.ai_review_model,
        api_key=api_key,
        cwd=str(Path.cwd()),
        max_steps=8,
        include_partial_messages=True,
        abort_event=abort_event,
        permission_gate=PermissionGate(permission_mode="deny"),
        tools=ToolRegistry(),
        allowed_tools=[],
        session_root=_default_session_root(),
    )

    parts: list[str] = []
    final_text: str | None = None
    async for e in query(prompt=prompt, options=options):
        if isinstance(e, AssistantDelta) and e.text_delta:
            parts.append(e.text_delta)
            if on_delta is not None:
                on_delta(e.text_delta)
        if isinstance(e, Result):
            if isinstance(e.final_text, str) and e.final_text:
                final_text = e.final_text
            break

    text = (final_text or "".join(parts)).strip() or "(empty)"
    return ReviewResult(markdown=text, model=cfg.ai_review_model, generated_at=now)


def _extract_context_and_tool_traces(
    rollout_path: str,
    *,
    include_context_user_messages: bool,
    tool_text_limit: int = 2000,
    max_tool_events_per_turn: int = 40,
    max_context_items: int = 12,
    context_text_limit: int = 1200,
) -> tuple[list[tuple[str, str]], dict[int, list[str]]]:
    """Best-effort extract:

    - session_context: (role, text) list for system/developer-ish constraints (trimmed/redacted).
    - tool_traces: map turn_index -> list[str] of tool call/output events (trimmed/redacted).

    Turn indexing matches `parser.turns.load_turns` logic (user message boundaries and optional filtering of context blobs).
    """
    p = Path(rollout_path)
    session_context: list[tuple[str, str]] = []
    tool_traces: dict[int, list[str]] = {}
    if not p.exists() or not p.is_file():
        return session_context, tool_traces

    turn_idx = 0

    def add_context(role: str, text: str) -> None:
        nonlocal session_context
        if len(session_context) >= max_context_items:
            return
        s = _clip(_redact(text), context_text_limit).strip()
        if s:
            session_context.append((role, s))

    def add_tool(item: str) -> None:
        nonlocal tool_traces, turn_idx
        if turn_idx <= 0:
            return
        items = tool_traces.setdefault(turn_idx, [])
        if len(items) >= max_tool_events_per_turn:
            return
        items.append(item)

    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                for event in _coerce_events(obj):
                    kind = event["kind"]
                    if kind == "message":
                        role = event["role"]
                        content = event["content"]
                        if role == "user":
                            if (not include_context_user_messages) and _looks_like_context_blob(content):
                                continue
                            turn_idx += 1
                            tool_traces.setdefault(turn_idx, [])
                        elif role in ("system", "developer"):
                            add_context(role, content)
                        elif role == "tool":
                            add_tool(_clip(_redact(content), tool_text_limit))
                    elif kind == "tool_call":
                        name = event["name"]
                        args = event.get("arguments")
                        args_s = _clip(_redact(_jsonish(args)), tool_text_limit)
                        add_tool(f"call {name} args={args_s}")
                    elif kind == "tool_output":
                        name = event["name"]
                        out = event.get("output")
                        out_s = _clip(_redact(_jsonish(out)), tool_text_limit)
                        add_tool(f"result {name} output={out_s}")
    except OSError:
        return session_context, tool_traces

    # Drop empty tool trace entries to keep the prompt compact.
    tool_traces = {k: v for k, v in tool_traces.items() if v}
    return session_context, tool_traces


def _coerce_events(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict):
        return []

    out: list[dict[str, Any]] = []

    # Plain transcript.
    role = obj.get("role")
    content = obj.get("content")
    if isinstance(role, str) and isinstance(content, str):
        out.append({"kind": "message", "role": role.strip(), "content": content})
        return out

    msg = obj.get("message")
    if isinstance(msg, dict):
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(role, str) and isinstance(content, str):
            out.append({"kind": "message", "role": role.strip(), "content": content})
            return out

    # Some transcripts use "text".
    role = obj.get("role")
    text = obj.get("text")
    if isinstance(role, str) and isinstance(text, str):
        out.append({"kind": "message", "role": role.strip(), "content": text})
        return out

    # Codex CLI sessions jsonl.
    typ = obj.get("type")
    payload = obj.get("payload")
    if isinstance(typ, str) and isinstance(payload, dict) and typ == "response_item":
        ptype = payload.get("type")
        if ptype == "message":
            role = payload.get("role")
            content = payload.get("content")
            text2 = _extract_text_from_content(content)
            if isinstance(role, str) and text2:
                out.append({"kind": "message", "role": role.strip(), "content": text2})
        elif ptype == "function_call":
            name = payload.get("name")
            if isinstance(name, str) and name.strip():
                out.append({"kind": "tool_call", "name": name.strip(), "arguments": payload.get("arguments")})
        elif ptype == "function_call_output":
            name = payload.get("name")
            if isinstance(name, str) and name.strip():
                out.append({"kind": "tool_output", "name": name.strip(), "output": payload.get("output")})

    return out


def _extract_text_from_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        typ = part.get("type")
        if typ in ("input_text", "output_text"):
            txt = part.get("text")
            if isinstance(txt, str) and txt.strip():
                parts.append(txt.strip())
    return "\n".join(parts).strip()


def _looks_like_context_blob(text: str) -> bool:
    s = text.lstrip()
    if s.startswith("<environment_context>"):
        return True
    if s.startswith("<permissions instructions>"):
        return True
    if s.startswith("<collaboration_mode>"):
        return True
    if s.startswith("# AGENTS.md instructions"):
        return True
    if s.startswith("<INSTRUCTIONS>"):
        return True
    if s.startswith("--- project-doc ---"):
        return True
    if s.startswith("<skill>"):
        return True
    return False


def _jsonish(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(obj)


def _clip(text: str, limit: int) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\n", " ").strip()
    return s if len(s) <= limit else (s[:limit] + "…(truncated)")


_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization:\\s*bearer\\s+)([^\\s]+)"), r"\\1***"),
    (re.compile(r"(?i)\\b(sk-[a-z0-9]{16,})\\b"), "***"),
    (re.compile(r"(?i)\\b(AKIA[0-9A-Z]{16})\\b"), "***"),
    (re.compile(r"(?i)\\b(xox[baprs]-[0-9A-Za-z-]{10,})\\b"), "***"),
    (
        re.compile(r"(?i)\\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\\b\\s*[:=]\\s*['\\\"]?([^\\s'\\\";]+)"),
        r"\\1=***",
    ),
    (re.compile(r"-----BEGIN [^-]+ PRIVATE KEY-----[\\s\\S]+?-----END [^-]+ PRIVATE KEY-----"), "***"),
]


def _redact(text: str) -> str:
    s = text or ""
    for pat, repl in _REDACT_PATTERNS:
        s = pat.sub(repl, s)
    return s
