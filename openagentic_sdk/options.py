from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .hooks.engine import HookEngine
from .permissions.gate import PermissionGate
from .providers.base import Provider
from .sessions.store import FileSessionStore
from .tools.defaults import default_tool_registry
from .tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class AgentExecutorDefinition:
    kind: str = "local"
    node_name: str | None = None


@dataclass(frozen=True, slots=True)
class AgentWorkspaceDefinition:
    mode: str = "readwrite"


@dataclass(frozen=True, slots=True)
class AgentWorkerDefinition:
    profile: str | None = None
    image: str | None = None
    max_concurrent_tasks: int = 3


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    description: str
    prompt: str
    tools: Sequence[str] = ()
    provider: Optional[Provider] = None
    provider_spec: Any | None = None
    model: Optional[str] = None
    executor: AgentExecutorDefinition = field(default_factory=AgentExecutorDefinition)
    workspace: AgentWorkspaceDefinition = field(default_factory=AgentWorkspaceDefinition)
    worker: AgentWorkerDefinition = field(default_factory=AgentWorkerDefinition)


@dataclass(frozen=True, slots=True)
class CompactionOptions:
    # Auto-compaction is only effective when `context_limit > 0`.
    auto: bool = True
    prune: bool = True

    # Model context window size (tokens). If 0, treat as unlimited and do not auto-compact.
    context_limit: int = 0

    # Model max output tokens. If unset, we fall back to `global_output_cap`.
    output_limit: int | None = None

    # Product-level cap on output tokens reserved from the context window.
    global_output_cap: int = 4096

    # OpenCode parity: reserve this many output tokens from the usable input
    # window. If unset, we derive it as min(20_000, max_output_tokens).
    reserved: int | None = None

    # OpenCode parity: some models specify a distinct input limit; when set we
    # prefer it over `context_limit` for overflow math.
    input_limit: int | None = None

    # Soft compaction: keep this many estimated tool-output tokens unpruned.
    protect_tool_output_tokens: int = 40_000

    # Only apply pruning if we'd prune at least this many estimated tokens.
    min_prune_tokens: int = 20_000


@dataclass(frozen=True, slots=True)
class OpenAgenticOptions:
    provider: Provider
    model: str
    api_key: str | None = None

    cwd: str = field(default_factory=os.getcwd)
    max_steps: int = 50
    timeout_s: float | None = None
    include_partial_messages: bool = False
    abort_event: Any | None = None

    tools: ToolRegistry = field(default_factory=default_tool_registry)
    allowed_tools: Sequence[str] | None = None

    permission_gate: PermissionGate = field(default_factory=lambda: PermissionGate(permission_mode="deny"))
    hooks: HookEngine = field(default_factory=HookEngine)

    session_store: FileSessionStore | None = None
    session_root: Path | None = None
    resume: str | None = None
    resume_max_events: int = 1000
    resume_max_bytes: int = 2_000_000

    setting_sources: Sequence[str] = ()
    project_dir: str | None = None

    # First-class system prompt injection (programmatic).
    # This is intentionally distinct from `.claude/CLAUDE.md` project memory.
    system_prompt: str | None = None

    # Extra instruction files to inject into the system prompt.
    # Entries are treated as paths (relative to `project_dir`/`cwd`) and may include glob patterns.
    instruction_files: Sequence[str] = ()

    # Compaction (context overflow handling). Defaults are aligned with the
    # COMPACTION.md portable design, but auto-triggering requires a non-zero
    # `context_limit`.
    compaction: CompactionOptions = field(default_factory=CompactionOptions)

    agents: Mapping[str, AgentDefinition] = field(default_factory=dict)
    remote_task_dispatcher: Any | None = None
    remote_chat_base_url: str | None = None
    remote_chat_timeout_s: float = 10.0

    # MCP placeholders (not implemented yet)
    mcp_servers: Mapping[str, Any] | None = None
    mcp_registry: Any | None = None
