from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

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
    lines.append("必要时参考 user 的输入，但不要展开工具输出/中间过程。")
    lines.append("")
    lines.append("输出要求（Markdown）：")
    lines.append("- 摘要（3-5 句）")
    lines.append("- 逐回合点评（按 turn 编号列出）")
    lines.append("- 问题与风险（指向具体 turn 编号与片段）")
    lines.append("- 改进建议（可执行）")
    lines.append("")
    lines.append("数据（turn 列表，仅含 user 输入与 assistant 最终回复）：")
    for t in turns:
        u = (t.user_text or "").strip()
        a = (t.assistant_text or "").strip()
        lines.append(f"Turn {t.index}:")
        lines.append(f"- User: {u}")
        lines.append(f"- Assistant(final): {a or '(empty)'}")
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
