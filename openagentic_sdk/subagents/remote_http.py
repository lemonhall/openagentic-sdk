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
from ..serialization import event_from_dict, event_to_dict
from ..sessions.store import FileSessionStore
from .remote_dispatch import resolve_git_head_only
from .remote_types import RemoteTaskRequest
from .remote_worker import InProcessRemoteTaskWorker

_STREAM_END = object()


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

    def make_server(self) -> ThreadingHTTPServer:
        worker = InProcessRemoteTaskWorker(base_options=self._base_options, session_store=self._session_store)
        repo_root = self._repo_root
        node_name = self._node_name

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
                    },
                )

            def do_POST(self):  # noqa: N802
                if self.path != "/dispatch":
                    _write_json(self, 404, {"error": "not_found"})
                    return

                body = _read_json(self)
                if body is None:
                    return

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
                    handle = asyncio.run(worker.dispatch(effective_request))

                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("X-OA-Child-Session-ID", handle.child_session_id)
                    self.send_header("X-OA-Target-Node", handle.target_node)
                    self.send_header("X-OA-Git-Revision", handle.git_revision)
                    self.send_header("X-OA-Worker-Execution-ID", handle.worker_execution_id or "")
                    self.end_headers()

                    async def _stream() -> None:
                        async for event in handle.events:
                            raw = json.dumps(event_to_dict(event), ensure_ascii=False).encode("utf-8") + b"\n"
                            self.wfile.write(raw)
                            self.wfile.flush()

                    asyncio.run(_stream())
                except Exception as e:  # noqa: BLE001
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
        "model": definition.model,
        "executor": {
            "kind": definition.executor.kind,
            "node_name": definition.executor.node_name,
        },
        "workspace": {"mode": definition.workspace.mode},
        "worker": {
            "profile": definition.worker.profile,
            "image": definition.worker.image,
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

    return AgentDefinition(
        description=str(obj.get("description") or ""),
        prompt=str(obj.get("prompt") or ""),
        tools=tools,
        model=(str(obj.get("model")) if isinstance(obj.get("model"), str) else None),
        executor=AgentExecutorDefinition(
            kind=str(executor_obj.get("kind") or "local"),
            node_name=(str(executor_obj.get("node_name")) if isinstance(executor_obj.get("node_name"), str) else None),
        ),
        workspace=AgentWorkspaceDefinition(mode=str(workspace_obj.get("mode") or "readwrite")),
        worker=AgentWorkerDefinition(
            profile=(str(worker_obj.get("profile")) if isinstance(worker_obj.get("profile"), str) else None),
            image=(str(worker_obj.get("image")) if isinstance(worker_obj.get("image"), str) else None),
        ),
    )
