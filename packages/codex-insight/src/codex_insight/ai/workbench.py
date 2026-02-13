from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..config import InsightConfig
from ..db.cache_db import CacheDb
from .reviewer import _ensure_openagentic_sdk_importable  # noqa: PLC2701
from .workbench_tools import WorkbenchSnapshot, build_workbench_tools


@dataclass(frozen=True, slots=True)
class WorkbenchChatResult:
    final_text: str
    model: str
    generated_at: int
    oa_session_id: str


def _default_session_root() -> Path:
    return Path.home() / ".codex-insight" / "oa_sessions"


def _transcript_path(*, oa_session_id: str) -> Path:
    return _default_session_root() / "sessions" / oa_session_id / "transcript.jsonl"


def load_workbench_transcript(*, oa_session_id: str, limit: int = 200) -> list[tuple[str, str]]:
    p = _transcript_path(oa_session_id=oa_session_id)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[tuple[str, str]] = []
    for line in lines[-limit:]:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = obj.get("role")
        text = obj.get("text")
        if isinstance(role, str) and isinstance(text, str):
            out.append((role, text))
    return out


def get_or_create_workbench_oa_session_id(*, cache: CacheDb, codex_session_id: str) -> str:
    _ensure_openagentic_sdk_importable()
    from openagentic_sdk.sessions.store import FileSessionStore

    store = FileSessionStore(root_dir=_default_session_root())

    def create() -> str:
        return store.create_session(metadata={"type": "codex-insight-workbench", "codex_session_id": codex_session_id})

    rec = cache.get_or_create_workbench_chat(codex_session_id=codex_session_id, create_oa_session_id=create)
    return rec.oa_session_id


_WORKBENCH_SYSTEM_PROMPT = """
你是一个“Codex Session Insight 工作台”助手。

你的目标：
- 在现有 AI Review 报告基础上，进行二次/多次对话式迭代，提升报告质量与可操作性。
- 重点诊断 assistant 的执行过程是否走偏（目标→计划→动作→结果→偏差与原因），并给出可复用 workflow。
- 尝试将可复用的流程、规则沉淀成 AGENTS.md 风格的规范建议（必须/禁止/推荐，尽量简短）。
- 需要时可以产出可直接落盘的产物（例如 SKILL.md 草案 / workflow checklist / AGENTS.md 片段），并通过工具保存为 markdown 文件。

重要约束：
- 你看不到 assistant 的隐藏思考链路，不要臆测；只能基于可见消息和 tool trace 推断，并注明依据。
- 你只能通过本工作台提供的工具读取当前 session 的只读信息；不要假设能访问任意文件系统。
- 输出尽量结构化、可执行，避免空泛。

可用工具：
- InsightGetSnapshot：当前 session 的 turns/选择/rollout 路径等摘要
- InsightGetTurn：获取某个 turn 的完整 user/assistant(final)
- InsightReadRolloutTail：读取 rollout 文件末尾若干行（脱敏/截断）
- InsightGetCachedReview：读取缓存的 Review（scope/selection）
- InsightWriteArtifact：将产物写入 ~/.codex-insight/artifacts/<session>/ 下
""".strip()


_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s]+)"), r"\1***"),
    (re.compile(r"(?i)\b(sk-[a-z0-9]{16,})\b"), "***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*['\"]?([^\s'\";]+)"
        ),
        r"\1=***",
    ),
    (re.compile(r"-----BEGIN [^-]+ PRIVATE KEY-----[\s\S]+?-----END [^-]+ PRIVATE KEY-----"), "***"),
]


def _redact(text: str) -> str:
    s = text or ""
    for pat, repl in _REDACT_PATTERNS:
        s = pat.sub(repl, s)
    return s


def _clip(text: str, limit: int) -> str:
    s = (text or "").strip()
    return s if len(s) <= limit else (s[:limit] + "…(truncated)")


def _dynamic_workbench_context(*, cache: CacheDb, snapshot: WorkbenchSnapshot) -> str:
    """Build a per-session context block to prevent 'I cannot see the report' confusion.

    This is injected into `system_prompt` so the persisted user transcript stays clean.
    """
    lines: list[str] = []
    lines.append("【工作台上下文（自动注入；只读）】")
    lines.append(f"- codex_session_id: {snapshot.codex_session_id}")
    if snapshot.rollout_path:
        lines.append(f"- rollout_path: {snapshot.rollout_path}")
    lines.append(f"- include_context_user_messages: {bool(snapshot.include_context_user_messages)}")
    lines.append(f"- selected_turn_indices: {list(snapshot.selected_turn_indices)}")
    lines.append("")

    cached_session = cache.get_review_scoped(session_id=snapshot.codex_session_id, scope="session", selection="all")
    if cached_session is not None:
        lines.append("【最新缓存 Review：整段 session（a 生成）】")
        lines.append(f"- model: {cached_session.model}")
        lines.append(f"- analyzed_at: {cached_session.analyzed_at}")
        lines.append("")
        lines.append(_clip(_redact(cached_session.review_markdown), 12_000))
        lines.append("")
    else:
        lines.append("【最新缓存 Review：整段 session】暂无（可在 UI 按 a 生成）")
        lines.append("")

    if snapshot.selected_turn_indices:
        sel = ",".join(str(x) for x in snapshot.selected_turn_indices)
        cached_sel = cache.get_review_scoped(session_id=snapshot.codex_session_id, scope="selection", selection=sel)
        if cached_sel is not None:
            lines.append(f"【最新缓存 Review：所选 turns（R 生成；selection={sel}）】")
            lines.append(f"- model: {cached_sel.model}")
            lines.append(f"- analyzed_at: {cached_sel.analyzed_at}")
            lines.append("")
            lines.append(_clip(_redact(cached_sel.review_markdown), 12_000))
            lines.append("")

    lines.append("说明：用户提到“最新报告/这份报告”，默认指上面缓存 Review。若需更细粒度，请调用 InsightGetCachedReview。")
    return "\n".join(lines).strip()


async def workbench_chat_stream(
    *,
    cfg: InsightConfig,
    cache: CacheDb,
    oa_session_id: str,
    snapshot: WorkbenchSnapshot,
    user_text: str,
    on_delta: Callable[[str], None] | None = None,
    abort_event: Any | None = None,
) -> WorkbenchChatResult:
    _ensure_openagentic_sdk_importable()
    try:
        from openagentic_sdk import OpenAgenticOptions, query
        from openagentic_sdk.events import AssistantDelta, Result
        from openagentic_sdk.permissions.gate import PermissionGate
        from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
        from openagentic_sdk.tools.registry import ToolRegistry
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Workbench 对话需要 openagentic-sdk 可用。") from e

    api_key = (cfg.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("未发现 API Key：请设置 RIGHTCODE_API_KEY / OPENAI_API_KEY，或配置 ~/.codex-insight/config.toml。")

    provider = OpenAIResponsesProvider(base_url=cfg.ai_base_url, timeout_s=120.0)
    tools = build_workbench_tools(snapshot=snapshot, cache=cache)
    tool_registry = ToolRegistry(tools)
    system_prompt = _WORKBENCH_SYSTEM_PROMPT + "\n\n" + _dynamic_workbench_context(cache=cache, snapshot=snapshot)

    options = OpenAgenticOptions(
        provider=provider,
        model=cfg.ai_review_model,
        api_key=api_key,
        cwd=str(Path.cwd()),
        max_steps=20,
        include_partial_messages=True,
        abort_event=abort_event,
        system_prompt=system_prompt,
        permission_gate=PermissionGate(permission_mode="bypass"),
        tools=tool_registry,
        allowed_tools=[t.name for t in tools],
        session_root=_default_session_root(),
        resume=oa_session_id,
    )

    now = int(time.time())
    parts: list[str] = []
    final_text: str | None = None
    async for e in query(prompt=user_text, options=options):
        if isinstance(e, AssistantDelta) and e.text_delta:
            parts.append(e.text_delta)
            if on_delta is not None:
                on_delta(e.text_delta)
        if isinstance(e, Result):
            if isinstance(e.final_text, str) and e.final_text:
                final_text = e.final_text
            break

    cache.touch_workbench_chat(codex_session_id=snapshot.codex_session_id)
    text = (final_text or "".join(parts)).strip() or "(empty)"
    return WorkbenchChatResult(final_text=text, model=cfg.ai_review_model, generated_at=now, oa_session_id=oa_session_id)
