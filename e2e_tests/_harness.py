from __future__ import annotations

import asyncio
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.options import AgentDefinition, OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.openai_responses import OpenAIResponsesProvider
from openagentic_sdk.sessions.store import FileSessionStore

_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    # User-local .env convention.
    "RIGHTCODE_API_KEY": ("OPENAI_API_KEY",),
    "RIGHTCODE_BASE_URL": ("OPENAI_BASE_URL",),
}


def _maybe_load_dotenv() -> None:
    """Best-effort .env loader (no third-party deps).

    This keeps real-network e2e tests easy to run locally while avoiding
    committing secrets (ensure `.env` is gitignored).
    """

    root = Path(__file__).resolve().parents[1]
    p = root / ".env"
    if not p.exists() or not p.is_file():
        return

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        if not key:
            continue
        val = v.strip()
        if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
            val = val[1:-1]
        if key and key not in os.environ and val:
            os.environ[key] = val


_maybe_load_dotenv()


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v
    for alt in _ENV_ALIASES.get(name, ()):
        v2 = os.environ.get(alt)
        if v2:
            os.environ[name] = v2
            return v2
    raise RuntimeError(
        f"Missing required env var: {name}\n"
        "These are real-network e2e tests.\n"
        "Set RIGHTCODE_API_KEY (or OPENAI_API_KEY) and optionally RIGHTCODE_BASE_URL/OPENAI_BASE_URL/RIGHTCODE_MODEL/RIGHTCODE_TIMEOUT_S then rerun."
    )


def _env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    if v is not None and v.strip():
        return v
    for alt in _ENV_ALIASES.get(name, ()):
        v2 = os.environ.get(alt)
        if v2 is not None and v2.strip():
            return v2
    return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    try:
        return float(v)
    except ValueError:
        return default


_HTTP_STATUS_RE = re.compile(r"\bHTTP\s+(\d{3})\b")


def _retryable_provider_error(e: BaseException) -> bool:
    msg = str(e)
    m = _HTTP_STATUS_RE.search(msg)
    if m is None:
        return False
    try:
        code = int(m.group(1))
    except ValueError:
        return False
    return code in (408, 409, 425, 429, 500, 502, 503, 504)


def _backoff_seconds(attempt_index: int, base: float) -> float:
    if attempt_index < 0:
        return 0.0
    return max(0.0, base) * (2**attempt_index)


class _ResilientProvider:
    """Provider wrapper that retries transient upstream errors at the request level.

    Note: inner transports already implement per-request retries, but in practice
    gateways can still return bursts of retryable 5xx/429. Retrying the whole
    request (only when no stream events have been yielded yet) makes the real
    network e2e suite materially more stable.
    """

    def __init__(self, inner: OpenAIResponsesProvider, *, outer_retries: int, outer_backoff_s: float) -> None:
        self._inner = inner
        self.outer_retries = max(0, int(outer_retries))
        self.outer_backoff_s = max(0.0, float(outer_backoff_s))
        self.name = getattr(inner, "name", "openai-compatible")

    async def complete(self, **kwargs: Any) -> Any:  # pragma: no cover
        last: BaseException | None = None
        for attempt in range(self.outer_retries + 1):
            try:
                return await self._inner.complete(**kwargs)
            except RuntimeError as e:
                last = e
                if attempt < self.outer_retries and _retryable_provider_error(e):
                    await asyncio.sleep(_backoff_seconds(attempt, self.outer_backoff_s))
                    continue
                raise
        if last is not None:  # pragma: no cover
            raise last
        raise RuntimeError("provider complete failed")  # pragma: no cover

    async def stream(self, **kwargs: Any):
        last: BaseException | None = None
        for attempt in range(self.outer_retries + 1):
            yielded_any = False
            try:
                async for ev in self._inner.stream(**kwargs):
                    yielded_any = True
                    yield ev
                return
            except RuntimeError as e:
                last = e
                if yielded_any:
                    raise
                if attempt < self.outer_retries and _retryable_provider_error(e):
                    await asyncio.sleep(_backoff_seconds(attempt, self.outer_backoff_s))
                    continue
                raise
        if last is not None:  # pragma: no cover
            raise last


def make_provider() -> OpenAIResponsesProvider:
    base_url = _env_str("RIGHTCODE_BASE_URL", "https://www.right.codes/codex/v1").rstrip("/")
    timeout_s = _env_float("RIGHTCODE_TIMEOUT_S", 120.0)
    # Real-network e2e runs can see transient 5xx/429 spikes. Make retries a bit
    # more forgiving by default (can be overridden via env).
    max_retries = int(_env_str("RIGHTCODE_MAX_RETRIES", "6"))
    retry_backoff_s = _env_float("RIGHTCODE_RETRY_BACKOFF_S", 0.75)
    inner = OpenAIResponsesProvider(
        name="openai-compatible",
        base_url=base_url,
        timeout_s=timeout_s,
        max_retries=max_retries,
        retry_backoff_s=retry_backoff_s,
    )
    outer_retries = int(_env_str("RIGHTCODE_OUTER_RETRIES", "2"))
    outer_backoff_s = _env_float("RIGHTCODE_OUTER_BACKOFF_S", 2.0)
    return _ResilientProvider(inner, outer_retries=outer_retries, outer_backoff_s=outer_backoff_s)  # type: ignore[return-value]


def make_options(
    root: Path,
    *,
    allowed_tools: Sequence[str] | None,
    include_partial_messages: bool = False,
    hooks: HookEngine | None = None,
    mcp_servers: Mapping[str, Any] | None = None,
    agents: Mapping[str, AgentDefinition] | None = None,
) -> OpenAgenticOptions:
    api_key = require_env("RIGHTCODE_API_KEY")
    model = _env_str("RIGHTCODE_MODEL", "gpt-5.2")
    store = FileSessionStore(root_dir=root)

    opts = OpenAgenticOptions(
        provider=make_provider(),
        model=model,
        api_key=api_key,
        cwd=str(root),
        project_dir=str(root),
        session_store=store,
        permission_gate=PermissionGate(permission_mode="bypass"),
        allowed_tools=list(allowed_tools) if allowed_tools is not None else None,
        include_partial_messages=include_partial_messages,
        hooks=hooks or HookEngine(),
        mcp_servers=dict(mcp_servers) if mcp_servers is not None else None,
        agents=dict(agents) if agents is not None else {},
    )
    return replace(opts, max_steps=30)
