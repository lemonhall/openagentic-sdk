from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
)
from .providers.base import Provider
from .providers.openai_compatible import OpenAICompatibleProvider
from .providers.openai_responses import OpenAIResponsesProvider

_REMOTE_CLUSTER_PROVIDER_TIMEOUT_S = 180.0


@dataclass(frozen=True, slots=True)
class ResolvedRemoteProviderSpec:
    provider_name: str
    kind: str
    base_url: str
    api_key: str
    api_key_header: str = "authorization"


@dataclass(frozen=True, slots=True)
class RemoteClusterSelfCheck:
    provider_ready: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RemoteClusterBootstrap:
    config_source: str
    host_provider: Provider | None
    host_provider_spec: ResolvedRemoteProviderSpec | None
    host_model: str
    agents: Mapping[str, AgentDefinition]
    provider_profiles: tuple[str, ...]
    self_check: RemoteClusterSelfCheck


class UnavailableRemoteProvider:
    name = "remote-provider-unavailable"

    async def complete(self, *, model, messages=None, input=None, tools=(), api_key=None, **kwargs):
        _ = (model, messages, input, tools, api_key, kwargs)
        raise RuntimeError("remote cluster provider is not ready")

    async def stream(self, *, model, messages=None, input=None, tools=(), api_key=None, **kwargs):
        _ = (model, messages, input, tools, api_key, kwargs)
        if False:  # pragma: no cover
            yield None
        raise RuntimeError("remote cluster provider is not ready")


def build_remote_cluster_routing_system_prompt(agents: Mapping[str, AgentDefinition]) -> str | None:
    rendered_agents: list[str] = []
    research_agents: list[str] = []
    writer_agents: list[str] = []

    for agent_name, raw_definition in agents.items():
        if not isinstance(agent_name, str) or not agent_name.strip():
            continue
        if not isinstance(raw_definition, AgentDefinition):
            continue
        name = agent_name.strip()
        rendered_agents.append(_render_remote_agent_line(name=name, definition=raw_definition))
        if _looks_like_research_agent(name=name, definition=raw_definition):
            research_agents.append(name)
        if _looks_like_writer_agent(name=name, definition=raw_definition):
            writer_agents.append(name)

    if not rendered_agents:
        return None

    lines = [
        "Remote cluster routing mode is enabled.",
        "The following configured remote agents are available in this cluster:",
        *rendered_agents,
        "",
        "Routing policy:",
        "- If the user explicitly names an agent, obey that choice when the agent exists.",
        "- Do not ask the user whether to delegate; decide that yourself.",
    ]
    if research_agents:
        lines.append(
            "- Delegate open-ended research, latest/current events, ongoing situations, external fact gathering, "
            f"or online investigation to {_format_agent_names(research_agents)} before doing host-side "
            "WebSearch/WebFetch yourself."
        )
    if writer_agents:
        lines.append(
            "- Delegate drafting, summarization, rewriting, and turning existing material into prose to "
            f"{_format_agent_names(writer_agents)} when that work can be completed independently."
        )
    lines.extend(
        [
            "- A serial route is valid: first delegate research, then delegate writing based on the research result.",
            "- Only fan out in parallel when the tasks are independent and atomic.",
            "- If you are not confident that delegation helps, do the work yourself.",
        ]
    )
    return "\n".join(lines)


def build_provider_from_spec(spec: ResolvedRemoteProviderSpec) -> Provider:
    if spec.kind == "openai_responses":
        return OpenAIResponsesProvider(
            name=spec.provider_name,
            base_url=spec.base_url,
            api_key_header=spec.api_key_header,
            timeout_s=_REMOTE_CLUSTER_PROVIDER_TIMEOUT_S,
        )
    if spec.kind == "openai_compatible":
        return OpenAICompatibleProvider(
            name=spec.provider_name,
            base_url=spec.base_url,
            api_key_header=spec.api_key_header,
            timeout_s=_REMOTE_CLUSTER_PROVIDER_TIMEOUT_S,
        )
    raise ValueError(f"Unsupported remote provider kind: {spec.kind}")


def load_remote_cluster_bootstrap(
    *,
    repo_root: str | Path,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> RemoteClusterBootstrap:
    repo_root = Path(repo_root)
    env_map = dict(env or os.environ)
    config_path = Path(config_path) if config_path is not None else (repo_root / "openagentic.remote.json")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("openagentic.remote.json must contain a JSON object")

    provider_defs = raw.get("providers")
    if not isinstance(provider_defs, Mapping):
        raise ValueError("openagentic.remote.json must define a 'providers' object")
    host_raw = raw.get("host")
    if not isinstance(host_raw, Mapping):
        raise ValueError("openagentic.remote.json must define a 'host' object")
    agents_raw = raw.get("agents")
    if not isinstance(agents_raw, Mapping):
        raise ValueError("openagentic.remote.json must define an 'agents' object")

    errors: list[str] = []
    host_profile_name = _as_non_empty_string(host_raw.get("provider")) or ""
    host_spec = _resolve_provider_spec(
        provider_name=host_profile_name,
        provider_defs=provider_defs,
        env_map=env_map,
        errors=errors,
    )
    host_model = _as_non_empty_string(host_raw.get("model")) or _default_model_for(host_profile_name, provider_defs)
    host_provider = build_provider_from_spec(host_spec) if host_spec is not None else None

    agents: dict[str, AgentDefinition] = {}
    for agent_name, agent_raw in agents_raw.items():
        if not isinstance(agent_name, str) or not agent_name.strip():
            continue
        if not isinstance(agent_raw, Mapping):
            errors.append(f"agent '{agent_name}' must be an object")
            continue
        provider_name = _as_non_empty_string(agent_raw.get("provider")) or host_profile_name
        provider_spec = _resolve_provider_spec(
            provider_name=provider_name,
            provider_defs=provider_defs,
            env_map=env_map,
            errors=errors,
            consumer_name=agent_name,
        )
        provider_obj = build_provider_from_spec(provider_spec) if provider_spec is not None else None
        tools_raw = agent_raw.get("tools")
        tools = tuple(str(item) for item in tools_raw) if isinstance(tools_raw, list) else ()
        executor_raw = agent_raw.get("executor")
        executor_raw = executor_raw if isinstance(executor_raw, Mapping) else {}
        workspace_raw = agent_raw.get("workspace")
        workspace_raw = workspace_raw if isinstance(workspace_raw, Mapping) else {}
        worker_raw = agent_raw.get("worker")
        worker_raw = worker_raw if isinstance(worker_raw, Mapping) else {}
        agents[agent_name] = AgentDefinition(
            description=_as_non_empty_string(agent_raw.get("description")) or agent_name,
            prompt=_as_non_empty_string(agent_raw.get("prompt")) or "",
            tools=tools,
            provider=provider_obj,
            provider_spec=provider_spec,
            model=_as_non_empty_string(agent_raw.get("model")) or _default_model_for(provider_name, provider_defs),
            executor=AgentExecutorDefinition(
                kind=_as_non_empty_string(executor_raw.get("kind")) or "local",
                node_name=_as_non_empty_string(executor_raw.get("node_name")),
            ),
            workspace=AgentWorkspaceDefinition(
                mode=_as_non_empty_string(workspace_raw.get("mode")) or "readwrite",
            ),
            worker=AgentWorkerDefinition(
                profile=_as_non_empty_string(worker_raw.get("profile")),
                image=_as_non_empty_string(worker_raw.get("image")),
                max_concurrent_tasks=int(worker_raw.get("max_concurrent_tasks") or 3),
            ),
        )

    return RemoteClusterBootstrap(
        config_source=str(config_path),
        host_provider=host_provider,
        host_provider_spec=host_spec,
        host_model=host_model,
        agents=agents,
        provider_profiles=tuple(sorted(str(name) for name in provider_defs.keys() if isinstance(name, str))),
        self_check=RemoteClusterSelfCheck(provider_ready=not errors, errors=tuple(errors)),
    )


def _resolve_provider_spec(
    *,
    provider_name: str,
    provider_defs: Mapping[str, Any],
    env_map: Mapping[str, str],
    errors: list[str],
    consumer_name: str = "host",
) -> ResolvedRemoteProviderSpec | None:
    if not provider_name:
        errors.append(f"{consumer_name}: missing provider profile name")
        return None
    raw = provider_defs.get(provider_name)
    if not isinstance(raw, Mapping):
        errors.append(f"{consumer_name}: unknown provider profile '{provider_name}'")
        return None
    kind = _as_non_empty_string(raw.get("kind")) or ""
    base_url_env = _as_non_empty_string(raw.get("base_url_env")) or ""
    api_key_env = _as_non_empty_string(raw.get("api_key_env")) or ""
    api_key_header = _as_non_empty_string(raw.get("api_key_header")) or "authorization"
    base_url = env_map.get(base_url_env, "") if base_url_env else ""
    api_key = env_map.get(api_key_env, "") if api_key_env else ""
    if not kind:
        errors.append(f"{consumer_name}: provider profile '{provider_name}' missing kind")
        return None
    if not base_url:
        errors.append(f"{consumer_name}: missing env {base_url_env or '<base_url_env>'} for provider '{provider_name}'")
        return None
    if not api_key:
        errors.append(f"{consumer_name}: missing env {api_key_env or '<api_key_env>'} for provider '{provider_name}'")
        return None
    return ResolvedRemoteProviderSpec(
        provider_name=provider_name,
        kind=kind,
        base_url=base_url,
        api_key=api_key,
        api_key_header=api_key_header,
    )


def _default_model_for(provider_name: str, provider_defs: Mapping[str, Any]) -> str:
    raw = provider_defs.get(provider_name)
    if isinstance(raw, Mapping):
        return _as_non_empty_string(raw.get("default_model")) or ""
    return ""


def _as_non_empty_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _render_remote_agent_line(*, name: str, definition: AgentDefinition) -> str:
    tools = ", ".join(str(item) for item in definition.tools) if definition.tools else "(inherit/default)"
    node_name = definition.executor.node_name or "(unspecified)"
    return (
        f'- `{name}`: {definition.description}; '
        f"tools: {tools}; executor: {definition.executor.kind}; node: {node_name}"
    )


def _format_agent_names(names: list[str]) -> str:
    unique_names = []
    for name in names:
        if name not in unique_names:
            unique_names.append(name)
    if not unique_names:
        return "the matching remote agent"
    return ", ".join(f"`{name}`" for name in unique_names)


def _looks_like_research_agent(*, name: str, definition: AgentDefinition) -> bool:
    tool_names = {str(item) for item in definition.tools}
    if "WebSearch" in tool_names or "WebFetch" in tool_names:
        return True
    haystack = " ".join([name, definition.description, definition.prompt]).lower()
    return any(
        token in haystack
        for token in (
            "research",
            "researcher",
            "search",
            "investigate",
            "investigation",
            "latest",
            "current",
            "status",
            "研究",
            "研究员",
            "搜索",
            "检索",
            "调研",
            "资料",
            "情报",
            "现状",
            "最新",
        )
    )


def _looks_like_writer_agent(*, name: str, definition: AgentDefinition) -> bool:
    haystack = " ".join([name, definition.description, definition.prompt]).lower()
    return any(
        token in haystack
        for token in (
            "writer",
            "writing",
            "draft",
            "summary",
            "summarize",
            "rewrite",
            "article",
            "essay",
            "写作",
            "撰写",
            "摘要",
            "总结",
            "整理",
            "改写",
            "文章",
            "小作文",
        )
    )
