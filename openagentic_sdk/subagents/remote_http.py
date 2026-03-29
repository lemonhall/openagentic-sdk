from __future__ import annotations

import asyncio
import json
import queue
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from ..remote_cluster_config import ResolvedRemoteProviderSpec, build_provider_from_spec
from ..serialization import event_from_dict, event_to_dict
from ..sessions.store import FileSessionStore
from .actor_lifecycle import RemoteWorkerStreamError
from .remote_dispatch import resolve_git_head_only
from .remote_types import RemoteTaskRequest
from .remote_worker import InProcessRemoteTaskWorker

_STREAM_END = object()
_REMOTE_STREAM_ERROR_KEY = "__oa_remote_stream_error__"


class HttpRemoteTaskDispatcher:
    def __init__(self, *, base_url: str, timeout_s: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def dispatch(self, request: RemoteTaskRequest):
        payload = _request_to_dict(request)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = urllib_request.Request(
            url=f"{self._base_url}/dispatch",
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = await asyncio.to_thread(urllib_request.urlopen, http_request, None, self._timeout_s)
        except urllib_error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Remote task dispatch failed with HTTP {e.code}: {body}") from e
        except urllib_error.URLError as e:
            raise RuntimeError(f"Remote task dispatch failed: {e.reason}") from e

        child_session_id = response.headers.get("X-OA-Child-Session-ID") or ""
        target_node = response.headers.get("X-OA-Target-Node") or ""
        git_revision = response.headers.get("X-OA-Git-Revision") or ""
        worker_execution_id = response.headers.get("X-OA-Worker-Execution-ID") or None
        if not child_session_id or not target_node or not git_revision:
            response.close()
            raise RuntimeError("Remote task dispatch returned incomplete metadata headers")
        _disable_response_read_timeout(response)

        q: queue.Queue[object] = queue.Queue()

        def _read_stream() -> None:
            try:
                while True:
                    line = response.readline()
                    if not line:
                        break
                    if isinstance(line, bytes):
                        text = line.decode("utf-8", errors="replace").strip()
                    else:
                        text = str(line).strip()
                    if not text:
                        continue
                    obj = json.loads(text)
                    if not isinstance(obj, dict):
                        raise RuntimeError("Remote task event stream yielded a non-object JSON line")
                    remote_stream_error = _remote_stream_error_from_payload(obj)
                    if remote_stream_error is not None:
                        raise remote_stream_error
                    q.put(event_from_dict(obj))
            except Exception as e:  # noqa: BLE001
                q.put(e)
            finally:
                try:
                    response.close()
                except Exception:  # noqa: BLE001
                    pass
                q.put(_STREAM_END)

        threading.Thread(target=_read_stream, name="oa-remote-http-stream", daemon=True).start()

        async def _events():
            while True:
                item = await asyncio.to_thread(q.get)
                if item is _STREAM_END:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item

        return request.make_handle(
            child_session_id=child_session_id,
            target_node=target_node,
            git_revision=git_revision,
            worker_execution_id=worker_execution_id,
            events=_events(),
        )


class RemoteTaskHttpWorkerServer:
    def __init__(
        self,
        *,
        base_options: OpenAgenticOptions,
        session_store: FileSessionStore,
        repo_root: str,
        node_name: str,
        host: str = "127.0.0.1",
        port: int = 0,
        health_status: Mapping[str, Any] | None = None,
    ) -> None:
        self._base_options = replace(
            base_options,
            cwd=repo_root,
            project_dir=repo_root,
            session_store=session_store,
        )
        self._session_store = session_store
        self._repo_root = repo_root
        self._node_name = node_name
        self._host = host
        self._port = port
        self._health_status = dict(health_status or {})

    def make_server(self) -> ThreadingHTTPServer:
        worker = InProcessRemoteTaskWorker(base_options=self._base_options, session_store=self._session_store)
        repo_root = self._repo_root
        node_name = self._node_name
        health_status = {"deployment_mode": "smoke", **dict(self._health_status)}
        execution_slots: threading.BoundedSemaphore | None = None
        execution_slot_limit: int | None = None
        execution_slots_lock = threading.Lock()

        def _execution_slots_for(limit: int) -> threading.BoundedSemaphore:
            nonlocal execution_slots
            nonlocal execution_slot_limit
            if limit <= 0:
                raise RuntimeError("worker max_concurrent_tasks must be positive")
            with execution_slots_lock:
                if execution_slots is None:
                    execution_slots = threading.BoundedSemaphore(limit)
                    execution_slot_limit = limit
                elif execution_slot_limit != limit:
                    raise RuntimeError(
                        "remote worker max_concurrent_tasks mismatch: "
                        f"existing {execution_slot_limit}, requested {limit}"
                    )
                assert execution_slots is not None
                return execution_slots

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path != "/health":
                    _write_json(self, 404, {"error": "not_found"})
                    return
                _write_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "node_name": node_name,
                        "git_revision": resolve_git_head_only(cwd=repo_root),
                        **health_status,
                    },
                )

            def do_POST(self):  # noqa: N802
                if self.path != "/dispatch":
                    _write_json(self, 404, {"error": "not_found"})
                    return

                body = _read_json(self)
                if body is None:
                    return

                stream_started = False
                try:
                    request = _request_from_dict(body)
                    local_revision = resolve_git_head_only(cwd=repo_root)
                    if request.git_revision != local_revision:
                        raise RuntimeError(
                            f"Remote worker git revision mismatch: requested {request.git_revision}, local {local_revision}"
                        )
                    requested_node = request.definition.executor.node_name or ""
                    if requested_node and requested_node != node_name:
                        raise RuntimeError(
                            f"Remote worker node mismatch: requested {requested_node}, local {node_name}"
                        )

                    effective_request = replace(
                        request,
                        definition=replace(
                            request.definition,
                            executor=replace(request.definition.executor, node_name=node_name),
                        ),
                        cwd=repo_root,
                        project_dir=repo_root,
                    )
                    slots = _execution_slots_for(effective_request.definition.worker.max_concurrent_tasks)
                    slots.acquire()
                    try:
                        handle = asyncio.run(worker.dispatch(effective_request))

                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                        self.send_header("X-OA-Child-Session-ID", handle.child_session_id)
                        self.send_header("X-OA-Target-Node", handle.target_node)
                        self.send_header("X-OA-Git-Revision", handle.git_revision)
                        self.send_header("X-OA-Worker-Execution-ID", handle.worker_execution_id or "")
                        self.end_headers()
                        stream_started = True

                        async def _stream() -> None:
                            async for event in handle.events:
                                raw = json.dumps(event_to_dict(event), ensure_ascii=False).encode("utf-8") + b"\n"
                                self.wfile.write(raw)
                                self.wfile.flush()

                        asyncio.run(_stream())
                    finally:
                        slots.release()
                except Exception as e:  # noqa: BLE001
                    if stream_started:
                        _write_remote_stream_error(self, e)
                        return
                    _write_json(self, 500, {"error": str(e)})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = format
                _ = args

        return ThreadingHTTPServer((self._host, self._port), Handler)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError:
        _write_json(handler, 400, {"error": "invalid_content_length"})
        return None
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    try:
        obj = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        _write_json(handler, 400, {"error": "invalid_json"})
        return None
    if not isinstance(obj, dict):
        _write_json(handler, 400, {"error": "invalid_request"})
        return None
    return obj


def _write_json(handler: BaseHTTPRequestHandler, status: int, obj: Mapping[str, Any]) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _request_to_dict(request: RemoteTaskRequest) -> dict[str, Any]:
    return {
        "parent_session_id": request.parent_session_id,
        "parent_tool_use_id": request.parent_tool_use_id,
        "agent_name": request.agent_name,
        "prompt": request.prompt,
        "definition": _definition_to_dict(request.definition),
        "cwd": request.cwd,
        "project_dir": request.project_dir,
        "git_revision": request.git_revision,
    }


def _request_from_dict(obj: Mapping[str, Any]) -> RemoteTaskRequest:
    return RemoteTaskRequest(
        parent_session_id=str(obj.get("parent_session_id") or ""),
        parent_tool_use_id=str(obj.get("parent_tool_use_id") or ""),
        agent_name=str(obj.get("agent_name") or ""),
        prompt=str(obj.get("prompt") or ""),
        definition=_definition_from_dict(obj.get("definition")),
        cwd=str(obj.get("cwd") or ""),
        project_dir=str(obj.get("project_dir") or "") or None,
        git_revision=str(obj.get("git_revision") or ""),
    )


def _definition_to_dict(definition: AgentDefinition) -> dict[str, Any]:
    return {
        "description": definition.description,
        "prompt": definition.prompt,
        "tools": list(definition.tools),
        "provider_spec": _provider_spec_to_dict(definition.provider_spec),
        "model": definition.model,
        "executor": {
            "kind": definition.executor.kind,
            "node_name": definition.executor.node_name,
        },
        "workspace": {"mode": definition.workspace.mode},
        "worker": {
            "profile": definition.worker.profile,
            "image": definition.worker.image,
            "max_concurrent_tasks": definition.worker.max_concurrent_tasks,
            "supervisor_policy": definition.worker.supervisor_policy,
        },
    }


def _definition_from_dict(raw: Any) -> AgentDefinition:
    obj = raw if isinstance(raw, Mapping) else {}
    executor_raw = obj.get("executor")
    executor_obj = executor_raw if isinstance(executor_raw, Mapping) else {}
    workspace_raw = obj.get("workspace")
    workspace_obj = workspace_raw if isinstance(workspace_raw, Mapping) else {}
    worker_raw = obj.get("worker")
    worker_obj = worker_raw if isinstance(worker_raw, Mapping) else {}

    tools_raw = obj.get("tools")
    tools = tuple(str(item) for item in tools_raw) if isinstance(tools_raw, (list, tuple)) else ()
    provider_spec = _provider_spec_from_dict(obj.get("provider_spec"))
    provider_obj = build_provider_from_spec(provider_spec) if provider_spec is not None else None

    return AgentDefinition(
        description=str(obj.get("description") or ""),
        prompt=str(obj.get("prompt") or ""),
        tools=tools,
        provider=provider_obj,
        provider_spec=provider_spec,
        model=(str(obj.get("model")) if isinstance(obj.get("model"), str) else None),
        executor=AgentExecutorDefinition(
            kind=str(executor_obj.get("kind") or "local"),
            node_name=(str(executor_obj.get("node_name")) if isinstance(executor_obj.get("node_name"), str) else None),
        ),
        workspace=AgentWorkspaceDefinition(mode=str(workspace_obj.get("mode") or "readwrite")),
        worker=AgentWorkerDefinition(
            profile=(str(worker_obj.get("profile")) if isinstance(worker_obj.get("profile"), str) else None),
            image=(str(worker_obj.get("image")) if isinstance(worker_obj.get("image"), str) else None),
            max_concurrent_tasks=int(worker_obj.get("max_concurrent_tasks") or 3),
            supervisor_policy=(
                str(worker_obj.get("supervisor_policy"))
                if isinstance(worker_obj.get("supervisor_policy"), str)
                else "fail_parent_tool_use"
            ),
        ),
    )


def _provider_spec_to_dict(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, ResolvedRemoteProviderSpec):
        return {
            "provider_name": raw.provider_name,
            "kind": raw.kind,
            "base_url": raw.base_url,
            "api_key": raw.api_key,
            "api_key_header": raw.api_key_header,
        }
    if isinstance(raw, Mapping):
        provider_name = raw.get("provider_name")
        kind = raw.get("kind")
        base_url = raw.get("base_url")
        api_key = raw.get("api_key")
        api_key_header = raw.get("api_key_header") or "authorization"
        if all(isinstance(item, str) and item for item in (provider_name, kind, base_url, api_key)):
            return {
                "provider_name": provider_name,
                "kind": kind,
                "base_url": base_url,
                "api_key": api_key,
                "api_key_header": api_key_header if isinstance(api_key_header, str) else "authorization",
            }
    return None


def _provider_spec_from_dict(raw: Any) -> ResolvedRemoteProviderSpec | None:
    obj = raw if isinstance(raw, Mapping) else {}
    provider_name = obj.get("provider_name")
    kind = obj.get("kind")
    base_url = obj.get("base_url")
    api_key = obj.get("api_key")
    api_key_header = obj.get("api_key_header") or "authorization"
    if not all(isinstance(item, str) and item for item in (provider_name, kind, base_url, api_key)):
        return None
    return ResolvedRemoteProviderSpec(
        provider_name=provider_name,
        kind=kind,
        base_url=base_url,
        api_key=api_key,
        api_key_header=api_key_header if isinstance(api_key_header, str) and api_key_header else "authorization",
    )


def _disable_response_read_timeout(response: Any) -> None:
    fp = getattr(response, "fp", None)
    raw = getattr(fp, "raw", None)
    sock = getattr(raw, "_sock", None)
    settimeout = getattr(sock, "settimeout", None)
    if callable(settimeout):
        try:
            settimeout(None)
        except OSError:
            return


def _write_remote_stream_error(handler: BaseHTTPRequestHandler, exc: Exception) -> None:
    payload = {
        _REMOTE_STREAM_ERROR_KEY: {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        handler.wfile.write(raw)
        handler.wfile.flush()
    except OSError:
        return


def _remote_stream_error_from_payload(obj: Mapping[str, Any]) -> RuntimeError | None:
    raw = obj.get(_REMOTE_STREAM_ERROR_KEY)
    if not isinstance(raw, Mapping):
        return None
    error_type = raw.get("error_type")
    error_message = raw.get("error_message")
    type_text = error_type if isinstance(error_type, str) and error_type else "RemoteWorkerError"
    message_text = error_message if isinstance(error_message, str) and error_message else "unknown remote stream failure"
    return RemoteWorkerStreamError(error_type=type_text, error_message=message_text)
