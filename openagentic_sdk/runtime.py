from __future__ import annotations

# Thin compatibility layer: runtime implementation moved to runtime_core/.

from .runtime_core.agent_runtime import AgentRuntime
from .runtime_core.common import (
    RunResult,
    _build_project_system_prompt,
    _maybe_expand_execute_skill_prompt,
    _maybe_expand_list_skills_prompt,
)

__all__ = [
    "AgentRuntime",
    "RunResult",
    "_build_project_system_prompt",
    "_maybe_expand_execute_skill_prompt",
    "_maybe_expand_list_skills_prompt",
]
