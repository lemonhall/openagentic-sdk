from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...options import OpenAgenticOptions
from ...tools.openai import tool_schemas_for_openai
from ...tools.openai_responses import tool_schemas_for_responses


def select_tool_names(options: OpenAgenticOptions) -> list[str]:
    tool_names = options.tools.names()
    if options.agents and "Task" not in set(tool_names):
        tool_names = [*tool_names, "Task"]
    if options.allowed_tools is not None:
        allowed = set(options.allowed_tools)
        tool_names = [t for t in tool_names if t in allowed]
    return tool_names


def build_tool_schemas(
    *,
    options: OpenAgenticOptions,
    provider_protocol: str,
    tool_names: Sequence[str],
) -> Sequence[Mapping[str, Any]]:
    if provider_protocol == "legacy":
        return tool_schemas_for_openai(
            tool_names,
            registry=options.tools,
            context={"cwd": options.cwd, "project_dir": options.project_dir},
        )
    return tool_schemas_for_responses(
        tool_names,
        registry=options.tools,
        context={"cwd": options.cwd, "project_dir": options.project_dir},
    )

