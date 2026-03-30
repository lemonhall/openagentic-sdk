from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from openagentic_sdk.custom_tools import load_custom_tools
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.js_plugins import load_js_plugin_tools, split_plugin_specs
from openagentic_sdk.js_tools import load_js_tools
from openagentic_sdk.mcp.auth_store import McpAuthStore
from openagentic_sdk.mcp.credentials import McpCredentialStore
from openagentic_sdk.opencode_config import load_merged_config
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
    CompactionOptions,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.permissions.interactive import InteractiveApprover
from openagentic_sdk.plugins import load_plugins, merge_hook_engines, plugins_from_opencode_config
from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
from openagentic_sdk.providers.selection import parse_model_ref, resolve_provider_and_model
from openagentic_sdk.tools.defaults import default_tool_registry


def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise SystemExit(f"Missing required environment variable: {name}")
    return val


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise SystemExit(f"Invalid {name}={raw!r}; expected int") from e


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise SystemExit(f"Invalid {name}={raw!r}; expected float") from e


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def build_provider_rightcode() -> OpenAIResponsesProvider:
    return OpenAIResponsesProvider(
        name="openai-compatible",
        base_url=os.getenv("RIGHTCODE_BASE_URL", "https://www.right.codes/codex/v1"),
        timeout_s=_env_float("RIGHTCODE_TIMEOUT_S", 120.0),
        max_retries=_env_int("RIGHTCODE_MAX_RETRIES", 2),
        retry_backoff_s=_env_float("RIGHTCODE_RETRY_BACKOFF_S", 0.5),
    )


def _expect_optional_string(value: Any, *, field_name: str, agent_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    raise SystemExit(f"Invalid agent '{agent_name}': {field_name} must be a string")


def _expect_tool_list(value: Any, *, agent_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SystemExit(f"Invalid agent '{agent_name}': tools must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _expect_optional_positive_int(value: Any, *, field_name: str, agent_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SystemExit(f"Invalid agent '{agent_name}': {field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as e:
        raise SystemExit(f"Invalid agent '{agent_name}': {field_name} must be a positive integer") from e
    if parsed <= 0:
        raise SystemExit(f"Invalid agent '{agent_name}': {field_name} must be a positive integer")
    return parsed


def _build_agents_from_config(cfg: Mapping[str, Any] | None) -> dict[str, AgentDefinition]:
    if not isinstance(cfg, Mapping):
        return {}

    agent_cfg = cfg.get("agent")
    if not isinstance(agent_cfg, Mapping):
        return {}

    out: dict[str, AgentDefinition] = {}
    for name, raw_spec in agent_cfg.items():
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(raw_spec, Mapping):
            raise SystemExit(f"Invalid agent '{name}': definition must be an object")
        if raw_spec.get("mode") == "primary":
            continue

        prompt = _expect_optional_string(raw_spec.get("prompt"), field_name="prompt", agent_name=name)
        if not prompt:
            raise SystemExit(f"Invalid agent '{name}': prompt is required")

        description = _expect_optional_string(raw_spec.get("description"), field_name="description", agent_name=name) or name
        tools = _expect_tool_list(raw_spec.get("tools"), agent_name=name)
        model = _expect_optional_string(raw_spec.get("model"), field_name="model", agent_name=name)

        executor_raw = raw_spec.get("executor")
        if executor_raw is not None and not isinstance(executor_raw, Mapping):
            raise SystemExit(f"Invalid agent '{name}': executor must be an object")
        executor_raw = executor_raw or {}
        kind = _expect_optional_string(executor_raw.get("kind"), field_name="executor.kind", agent_name=name) or "local"
        if kind not in {"local", "k3s"}:
            raise SystemExit(f"Invalid agent '{name}': executor.kind must be 'local' or 'k3s'")
        node_name = _expect_optional_string(executor_raw.get("node_name"), field_name="executor.node_name", agent_name=name)
        if kind == "k3s" and not node_name:
            raise SystemExit(f"Invalid agent '{name}': executor.node_name is required for k3s agents")

        workspace_raw = raw_spec.get("workspace")
        if workspace_raw is not None and not isinstance(workspace_raw, Mapping):
            raise SystemExit(f"Invalid agent '{name}': workspace must be an object")
        workspace_raw = workspace_raw or {}
        workspace_mode = _expect_optional_string(workspace_raw.get("mode"), field_name="workspace.mode", agent_name=name)
        if kind == "k3s":
            workspace_mode = workspace_mode or "readonly"
            if workspace_mode != "readonly":
                raise SystemExit(f"Invalid agent '{name}': k3s agents must use workspace.mode='readonly'")
        else:
            workspace_mode = workspace_mode or "readwrite"

        worker_raw = raw_spec.get("worker")
        if worker_raw is not None and not isinstance(worker_raw, Mapping):
            raise SystemExit(f"Invalid agent '{name}': worker must be an object")
        worker_raw = worker_raw or {}
        worker_profile = _expect_optional_string(worker_raw.get("profile"), field_name="worker.profile", agent_name=name)
        worker_image = _expect_optional_string(worker_raw.get("image"), field_name="worker.image", agent_name=name)
        if worker_image is None:
            worker_image = _expect_optional_string(raw_spec.get("image"), field_name="image", agent_name=name)
        max_concurrent_tasks = _expect_optional_positive_int(
            worker_raw.get("max_concurrent_tasks"),
            field_name="worker.max_concurrent_tasks",
            agent_name=name,
        )

        out[name] = AgentDefinition(
            description=description,
            prompt=prompt,
            tools=tools,
            model=model,
            executor=AgentExecutorDefinition(kind=kind, node_name=node_name),
            workspace=AgentWorkspaceDefinition(mode=workspace_mode),
            worker=AgentWorkerDefinition(
                profile=worker_profile,
                image=worker_image,
                max_concurrent_tasks=max_concurrent_tasks or 3,
            ),
        )
    return out


def build_options(
    *,
    cwd: str,
    project_dir: str | None,
    permission_mode: str,
    allowed_tools: Sequence[str] | None = None,
    session_root: str | Path | None = None,
    resume: str | None = None,
    interactive: bool = False,
) -> OpenAgenticOptions:
    session_root_path: Path | None = None
    if session_root is not None:
        session_root_path = Path(session_root)

    gate = PermissionGate(
        permission_mode=permission_mode,
        interactive=interactive,
        interactive_approver=InteractiveApprover(input_fn=input) if interactive else None,
    )

    marker = "## OA CLI Context"
    platform = sys.platform
    project_dir2 = project_dir or cwd

    async def _inject_cli_context(payload: Mapping[str, Any]) -> HookDecision:
        msgs = payload.get("messages")
        if not isinstance(msgs, list) or not msgs:
            return HookDecision()

        block = "\n".join(
            [
                marker,
                f"- platform: {platform}",
                f"- cwd: {cwd}",
                f"- project_dir: {project_dir2}",
                "- These values are authoritative for this session.",
                "- If the user asks for the current directory, answer using `cwd` directly (do not guess).",
            ]
        ).strip()

        first = msgs[0] if isinstance(msgs[0], dict) else None
        if first and first.get("role") == "system" and isinstance(first.get("content"), str):
            content = first["content"]
            if marker in content:
                return HookDecision(action="noop")
            new_first = dict(first)
            new_first["content"] = block + "\n\n" + content
            return HookDecision(override_messages=[new_first, *msgs[1:]], action="inject_cli_context")

        return HookDecision(override_messages=[{"role": "system", "content": block}, *msgs], action="inject_cli_context")

    hooks = HookEngine(
        before_model_call=[HookMatcher(name="oa-cli-context", tool_name_pattern="*", hook=_inject_cli_context)],
        enable_message_rewrite_hooks=True,
    )

    # OpenCode parity: load opencode.json/opencode.jsonc (+ .opencode/) when present.
    cfg: dict = {}
    try:
        cfg = load_merged_config(cwd=project_dir2)
    except Exception:
        cfg = {}
    instructions = cfg.get("instructions") if isinstance(cfg, dict) else None
    instruction_files = list(instructions) if isinstance(instructions, list) else []

    compaction = CompactionOptions()
    comp_cfg = cfg.get("compaction") if isinstance(cfg, dict) else None
    if isinstance(comp_cfg, dict):
        compaction = CompactionOptions(
            auto=bool(comp_cfg.get("auto", compaction.auto)),
            prune=bool(comp_cfg.get("prune", compaction.prune)),
            context_limit=int(comp_cfg.get("context_limit", compaction.context_limit) or 0),
            reserved=(int(comp_cfg.get("reserved")) if isinstance(comp_cfg.get("reserved"), int) else None),
            input_limit=(int(comp_cfg.get("input_limit")) if isinstance(comp_cfg.get("input_limit"), int) else None),
        )

    # Plugins (OpenCode parity): merge plugin-provided hooks/tools.
    plugin_specs = plugins_from_opencode_config(cfg)
    py_plugin_specs, js_plugin_specs = split_plugin_specs(plugin_specs, project_dir=project_dir2) if plugin_specs else ([], [])
    loaded = load_plugins(py_plugin_specs, project_dir=project_dir2) if py_plugin_specs else None
    if loaded is not None:
        hooks = merge_hook_engines(hooks, loaded.hooks)

    tools = default_tool_registry()

    # Custom tools (OpenCode parity): load from on-disk tool directories.
    try:
        for t in load_custom_tools(project_dir=project_dir2):
            tools.register(t)
    except Exception:
        pass

    # JS/TS custom tools (OpenCode parity): disabled by default (explicit opt-in).
    experimental = cfg.get("experimental") if isinstance(cfg, dict) else None
    js_tools_enabled = False
    if isinstance(experimental, dict):
        js_tools_enabled = bool(experimental.get("js_tools") or experimental.get("jsTools"))
    js_tools_enabled = bool(js_tools_enabled or _env_bool("OA_ENABLE_JS_TOOLS", default=False))
    try:
        for t in load_js_tools(project_dir=project_dir2, enabled=js_tools_enabled):
            tools.register(t)
    except Exception:
        pass

    # Plugin tools (OpenCode parity): register after custom tools.
    if loaded is not None:
        for t in loaded.tools:
            tools.register(t)

    # JS/TS plugin tools (OpenCode parity): file:// only, disabled by default.
    js_plugins_enabled = False
    if isinstance(experimental, dict):
        js_plugins_enabled = bool(experimental.get("js_plugins") or experimental.get("jsPlugins"))
    js_plugins_enabled = bool(js_plugins_enabled or _env_bool("OA_ENABLE_JS_PLUGINS", default=False))
    if js_plugins_enabled and js_plugin_specs:
        try:
            for t in load_js_plugin_tools(plugin_specs=js_plugin_specs, project_dir=project_dir2, enabled=True):
                tools.register(t)
        except Exception:
            pass

    # MCP servers (OpenCode parity): load from config and merge stored credentials.
    mcp_servers: dict[str, object] | None = None
    mcp_cfg = cfg.get("mcp") if isinstance(cfg, dict) else None
    if isinstance(mcp_cfg, dict) and mcp_cfg:
        store = McpCredentialStore.load_default()
        auth_store = McpAuthStore.load_default()
        mcp_servers = {}
        for key, spec in mcp_cfg.items():
            if not isinstance(key, str) or not key:
                continue
            if not isinstance(spec, dict):
                continue
            typ = spec.get("type")
            if typ == "local":
                cmd = spec.get("command")
                env = spec.get("environment") if isinstance(spec.get("environment"), dict) else None
                if isinstance(cmd, list) and all(isinstance(x, str) and x for x in cmd):
                    mcp_servers[key] = {"type": "local", "command": list(cmd), "environment": env or {}}
            if typ == "remote":
                url = spec.get("url")
                if not isinstance(url, str) or not url:
                    continue
                headers = spec.get("headers") if isinstance(spec.get("headers"), dict) else None
                base = {str(k): str(v) for k, v in (headers or {}).items()}

                # Prefer OAuth access tokens (mcp-auth.json) if present and URL matches.
                entry = auth_store.get_for_url(key, server_url=url)
                if entry is not None and entry.tokens is not None:
                    if entry.tokens.access_token and "authorization" not in {k.lower() for k in base.keys()}:
                        base["Authorization"] = f"Bearer {entry.tokens.access_token}"

                merged = store.merged_headers(key, base)
                mcp_servers[key] = {"type": "remote", "url": url, "headers": merged}

    provider_obj = build_provider_rightcode()
    api_key_val = os.getenv("RIGHTCODE_API_KEY")

    # OpenCode parity: model can be `provider/model`. If present, it is the
    # primary selection mechanism and should override OA_PROVIDER heuristics.
    raw_model = cfg.get("model") if isinstance(cfg, dict) and isinstance(cfg.get("model"), str) else None
    if not raw_model:
        raw_model = os.getenv("RIGHTCODE_MODEL", "gpt-5.4")
    model_ref = parse_model_ref(raw_model)

    # Provider config (OpenCode parity, minimal): allow selecting a configured provider
    # via OA_PROVIDER when `provider.<name>.options.baseURL/apiKey` exists.
    prov_cfg = cfg.get("provider") if isinstance(cfg, dict) else None
    if model_ref.provider_id:
        resolved = resolve_provider_and_model(
            cfg=cfg if isinstance(cfg, dict) else None,
            model_ref=model_ref,
            base_provider=provider_obj,
            base_api_key=api_key_val,
        )
        provider_obj = resolved.provider
        api_key_val = resolved.api_key
    elif isinstance(prov_cfg, dict) and prov_cfg:
        selected = os.getenv("OA_PROVIDER")
        spec = prov_cfg.get(selected) if isinstance(selected, str) and selected in prov_cfg else None
        if spec is None and len(prov_cfg) == 1:
            spec = next(iter(prov_cfg.values()))
            selected = next(iter(prov_cfg.keys()))
        if isinstance(spec, dict):
            opts = spec.get("options")
            if isinstance(opts, dict):
                base_url = opts.get("baseURL")
                api_key = opts.get("apiKey")
                timeout_ms = opts.get("timeout")

                if isinstance(base_url, str) and base_url:
                    timeout_s = 120.0
                    if isinstance(timeout_ms, int) and timeout_ms > 0:
                        timeout_s = float(timeout_ms) / 1000.0
                    provider_obj = OpenAIResponsesProvider(
                        name=str(selected or "openai-compatible"),
                        base_url=base_url,
                        timeout_s=timeout_s,
                        max_retries=_env_int("RIGHTCODE_MAX_RETRIES", 2),
                        retry_backoff_s=_env_float("RIGHTCODE_RETRY_BACKOFF_S", 0.5),
                    )
                if isinstance(api_key, str) and api_key:
                    api_key_val = api_key

    # OpenCode parity: derive compaction token limits from model metadata when
    # the user did not specify explicit limits.
    if model_ref.provider_id and (int(compaction.context_limit or 0) <= 0 or compaction.output_limit is None):
        try:
            from openagentic_sdk.providers.models_dev import get_models_dev

            db = get_models_dev()
            p = db.get(str(model_ref.provider_id)) if isinstance(db, dict) else None
            models = p.get("models") if isinstance(p, dict) else None
            m = models.get(str(model_ref.model_id)) if isinstance(models, dict) else None
            lim = m.get("limit") if isinstance(m, dict) else None
            if isinstance(lim, dict):
                ctx_limit = int(lim.get("context") or 0)
                inp_limit_raw = lim.get("input")
                inp_limit = int(inp_limit_raw or 0) if isinstance(inp_limit_raw, int) else 0
                out_limit = int(lim.get("output") or 0)
                new_context_limit = compaction.context_limit
                new_input_limit = compaction.input_limit
                new_output_limit = compaction.output_limit
                if int(new_context_limit or 0) <= 0 and ctx_limit > 0:
                    new_context_limit = ctx_limit
                if new_output_limit is None and out_limit > 0:
                    new_output_limit = out_limit
                if new_input_limit is None and inp_limit > 0:
                    new_input_limit = inp_limit
                if (
                    new_context_limit != compaction.context_limit
                    or new_output_limit != compaction.output_limit
                    or new_input_limit != compaction.input_limit
                ):
                    compaction = CompactionOptions(
                        auto=compaction.auto,
                        prune=compaction.prune,
                        context_limit=int(new_context_limit or 0),
                        output_limit=new_output_limit,
                        global_output_cap=compaction.global_output_cap,
                        reserved=compaction.reserved,
                        input_limit=new_input_limit,
                        protect_tool_output_tokens=compaction.protect_tool_output_tokens,
                        min_prune_tokens=compaction.min_prune_tokens,
                    )
        except Exception:
            pass

    if not api_key_val:
        api_key_val = require_env("RIGHTCODE_API_KEY")

    agents = _build_agents_from_config(cfg if isinstance(cfg, dict) else None)

    return OpenAgenticOptions(
        provider=provider_obj,
        api_key=api_key_val,
        model=(model_ref.model_id if model_ref.provider_id else str(raw_model or "gpt-5.4")),
        cwd=cwd,
        project_dir=project_dir,
        tools=tools,
        allowed_tools=allowed_tools,
        permission_gate=gate,
        hooks=hooks,
        include_partial_messages=interactive,
        session_root=session_root_path,
        resume=resume,
        setting_sources=["project"],
        instruction_files=instruction_files,
        compaction=compaction,
        mcp_servers=mcp_servers,
        agents=agents,
    )
