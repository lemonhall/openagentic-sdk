from __future__ import annotations

from typing import Any, Mapping, Sequence

from .remote_dispatch import resolve_git_head_only


def try_resolve_git_revision(*, cwd: str) -> str | None:
    try:
        return resolve_git_head_only(cwd=cwd)
    except Exception:
        return None


def build_authoritative_session_metadata(
    *,
    cwd: str,
    provider_name: str,
    model: str,
    setting_sources: Sequence[str] = (),
    allowed_tools: Sequence[str] | None = None,
    extra: Mapping[str, Any] | None = None,
    host_node_name: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = dict(extra or {})
    metadata.setdefault("cwd", cwd)
    metadata.setdefault("provider_name", provider_name)
    metadata.setdefault("model", model)
    if setting_sources and "setting_sources" not in metadata:
        metadata["setting_sources"] = list(setting_sources)
    if allowed_tools is not None and "allowed_tools" not in metadata:
        metadata["allowed_tools"] = list(allowed_tools)
    revision = try_resolve_git_revision(cwd=cwd)
    if revision:
        metadata["git_revision"] = revision
        metadata["authoritative_revision"] = revision
    if host_node_name:
        metadata["host_node_name"] = host_node_name
    return metadata


def build_child_session_metadata(
    *,
    parent_session_id: str,
    parent_tool_use_id: str,
    agent_name: str,
    dispatch_mode: str,
    target_node: str | None,
    git_revision: str | None,
    worker_execution_id: str | None,
) -> dict[str, Any]:
    metadata = {
        "parent_session_id": parent_session_id,
        "parent_tool_use_id": parent_tool_use_id,
        "agent_name": agent_name,
        "dispatch_mode": dispatch_mode,
    }
    if target_node:
        metadata["target_node"] = target_node
    if git_revision:
        metadata["git_revision"] = git_revision
    if worker_execution_id:
        metadata["worker_execution_id"] = worker_execution_id
    return metadata
