from __future__ import annotations

from typing import Any, Mapping

from ..common import _base_system_role_for_model, _build_project_system_prompt
from ...options import OpenAgenticOptions


def inject_project_system_prompt(
    runtime: Any,
    *,
    options: OpenAgenticOptions,
    provider_protocol: str,
    messages: list[Mapping[str, Any]],
) -> None:
    built = _build_project_system_prompt(options)
    sys_prompt = built.system_text
    sys_role = _base_system_role_for_model(model_id=options.model, provider_protocol=provider_protocol)
    if built.is_codex_session:
        sys_role = "user"
    if sys_prompt:
        messages.insert(0, {"role": sys_role, "content": sys_prompt})

    runtime._base_system_prompt = sys_prompt
    runtime._base_system_role = sys_role if sys_prompt else None
    runtime._base_instructions = built.instructions

