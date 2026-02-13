from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..config import InsightConfig


@dataclass(frozen=True, slots=True)
class ReviewResult:
    markdown: str
    model: str
    generated_at: int


def _default_session_root() -> Path:
    return Path.home() / ".codex-insight" / "oa_sessions"


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


async def review_messages(*, cfg: InsightConfig, messages: list[dict[str, str]]) -> ReviewResult:
    try:
        from openagentic_sdk import OpenAgenticOptions, run
        from openagentic_sdk.permissions.gate import PermissionGate
        from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
        from openagentic_sdk.tools.registry import ToolRegistry
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "AI Review 需要安装 openagentic-sdk（以及正确配置 OPENAI_API_KEY / config.toml）。"
        ) from e

    api_key = (cfg.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("未配置 OpenAI API Key：请设置 OPENAI_API_KEY 或 config.toml 的 [ai].api_key。")

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

