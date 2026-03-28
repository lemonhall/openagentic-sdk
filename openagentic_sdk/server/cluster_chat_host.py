from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import queue
import threading
import time
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from ..options import OpenAgenticOptions
from ..permissions.gate import PermissionGate
from ..remote_cluster_config import UnavailableRemoteProvider, load_remote_cluster_bootstrap
from ..serialization import event_to_dict
from ..sessions.store import FileSessionStore
from ..subagents.git_sync import CommittedGitSynchronizer, GitSyncResult
from ..subagents.remote_http import HttpRemoteTaskDispatcher
from ..subagents.session_meta import build_authoritative_session_metadata, try_resolve_git_revision
from ..tools.defaults import default_tool_registry


def _parse_request_target(path: str) -> list[str]:
    from urllib.parse import urlparse

    parsed = urlparse(path or "")
    return [part for part in (parsed.path or "").split("/") if part]


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


def _write_json(handler: BaseHTTPRequestHandler, status: int, obj: Any) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _session_info(store: FileSessionStore, session_id: str) -> dict[str, Any] | None:
    record = store.read_meta_record(session_id)
    if not record:
        return None
    return {
        "id": session_id,
        "created_at": record.get("created_at"),
        "metadata": store.read_metadata(session_id),
    }


class _EventHub:
    def __init__(self) -> None:
        self._subs: list[queue.Queue[dict[str, Any]]] = []

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        try:
            self._subs.remove(q)
        except ValueError:
            pass

    def publish(self, obj: dict[str, Any]) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(obj)
            except Exception:
                continue


@dataclass(frozen=True, slots=True)
class ClusterChatHostServer:
    base_options: OpenAgenticOptions
    session_store: FileSessionStore
    host: str = "127.0.0.1"
    port: int = 0
    host_node_name: str | None = None
    git_synchronizer: CommittedGitSynchronizer | None = None
    health_status: Mapping[str, Any] | None = None

    def make_server(self) -> ThreadingHTTPServer:
        options = self.base_options
        store = self.session_store
        host_node_name = self.host_node_name or ""
        health_status = {"deployment_mode": "smoke", **dict(self.health_status or {})}
        hub = _EventHub()
        synchronizer = self.git_synchronizer or CommittedGitSynchronizer(authoritative_cwd=options.cwd)
        running_abort: dict[str, threading.Event] = {}
        running_lock = threading.Lock()

        def _sync_result_for_session(session_id: str) -> GitSyncResult:
            result = synchronizer.sync()
            patch: dict[str, Any] = {"last_sync_status": result.status}
            if result.reason:
                patch["last_sync_reason"] = result.reason
            target_revision = result.target_revision or try_resolve_git_revision(cwd=options.cwd)
            if target_revision:
                patch["git_revision"] = target_revision
                patch["authoritative_revision"] = target_revision
            try:
                store.update_metadata(session_id, patch=patch)
            except FileNotFoundError:
                pass
            return result

        def _start_prompt_async(*, session_id: str, prompt: str) -> None:
            abort_event = threading.Event()
            with running_lock:
                running_abort[session_id] = abort_event

            def _run() -> None:
                result = GitSyncResult(status="ok", target_revision=try_resolve_git_revision(cwd=options.cwd))
                try:
                    async def _query() -> None:
                        from ..api import query as query_events

                        opts2 = replace(
                            options,
                            resume=session_id,
                            session_store=store,
                            abort_event=abort_event,
                        )
                        async for event in query_events(prompt=prompt, options=opts2):
                            hub.publish(
                                {
                                    "type": "session.event",
                                    "session_id": session_id,
                                    "event": event_to_dict(event),
                                }
                            )

                    asyncio.run(_query())
                    result = _sync_result_for_session(session_id)
                except Exception as e:  # noqa: BLE001
                    result = GitSyncResult(
                        status="error",
                        target_revision=try_resolve_git_revision(cwd=options.cwd),
                        reason=str(e),
                    )
                finally:
                    with running_lock:
                        running_abort.pop(session_id, None)
                    hub.publish({"type": "session.sync", "session_id": session_id, "sync": result.to_dict()})

            threading.Thread(target=_run, name=f"oa-cluster-chat-{session_id}", daemon=True).start()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parts = _parse_request_target(self.path)
                if parts == ["health"]:
                    payload: dict[str, Any] = {"ok": True, "cwd": options.cwd}
                    revision = try_resolve_git_revision(cwd=options.cwd)
                    if revision:
                        payload["git_revision"] = revision
                    if host_node_name:
                        payload["host_node_name"] = host_node_name
                    payload.update(health_status)
                    _write_json(self, 200, payload)
                    return

                if parts == ["event"]:
                    self.close_connection = True
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()

                    q = hub.subscribe()
                    try:
                        self.wfile.write(b"data: {\"type\":\"server.connected\"}\n\n")
                        self.wfile.flush()
                        last_heartbeat = time.time()
                        while True:
                            try:
                                obj = q.get(timeout=0.5)
                                raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                                self.wfile.write(b"data: " + raw + b"\n\n")
                                self.wfile.flush()
                            except queue.Empty:
                                pass
                            if time.time() - last_heartbeat >= 30.0:
                                self.wfile.write(b"data: {\"type\":\"server.heartbeat\"}\n\n")
                                self.wfile.flush()
                                last_heartbeat = time.time()
                    except Exception:
                        return
                    finally:
                        hub.unsubscribe(q)

                if len(parts) == 2 and parts[0] == "session":
                    session_id = parts[1]
                    try:
                        _ = store.session_dir(session_id)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    info = _session_info(store, session_id)
                    if info is None:
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    _write_json(self, 200, info)
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "events":
                    session_id = parts[1]
                    try:
                        entries = [event_to_dict(event) for event in store.read_events(session_id)]
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    _write_json(self, 200, {"session_id": session_id, "entries": entries})
                    return

                _write_json(self, 404, {"error": "not_found"})

            def do_POST(self):  # noqa: N802
                parts = _parse_request_target(self.path)
                if parts == ["session"]:
                    body = _read_json(self)
                    if body is None:
                        return
                    metadata_raw = body.get("metadata")
                    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
                    title = body.get("title")
                    if isinstance(title, str) and title.strip():
                        metadata = {**metadata, "title": title.strip()}
                    session_metadata = build_authoritative_session_metadata(
                        cwd=options.cwd,
                        provider_name=getattr(options.provider, "name", "unknown"),
                        model=options.model,
                        setting_sources=options.setting_sources,
                        allowed_tools=options.allowed_tools,
                        extra=metadata,
                        host_node_name=host_node_name or None,
                    )
                    session_id = store.create_session(metadata=session_metadata)
                    _write_json(self, 200, _session_info(store, session_id) or {"id": session_id})
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "prompt_async":
                    session_id = parts[1]
                    try:
                        _ = store.session_dir(session_id)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    body = _read_json(self)
                    if body is None:
                        return
                    prompt = body.get("prompt") or body.get("text") or body.get("content")
                    if not isinstance(prompt, str) or not prompt:
                        _write_json(self, 400, {"error": "invalid_prompt"})
                        return
                    _start_prompt_async(session_id=session_id, prompt=prompt)
                    self.send_response(204)
                    self.end_headers()
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "abort":
                    session_id = parts[1]
                    with running_lock:
                        abort_event = running_abort.get(session_id)
                    if abort_event is not None:
                        abort_event.set()
                    _write_json(self, 200, {"ok": True})
                    return

                _write_json(self, 404, {"error": "not_found"})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = format
                _ = args

        return ThreadingHTTPServer((self.host, int(self.port)), Handler)


class StaticNodeHttpRemoteTaskDispatcher:
    def __init__(self, *, node_urls: Mapping[str, str], timeout_s: float = 60.0) -> None:
        self._dispatchers = {
            node_name: HttpRemoteTaskDispatcher(base_url=base_url, timeout_s=timeout_s)
            for node_name, base_url in node_urls.items()
        }

    async def dispatch(self, request):
        node_name = request.definition.executor.node_name or ""
        dispatcher = self._dispatchers.get(node_name)
        if dispatcher is None:
            raise RuntimeError(f"no remote worker URL configured for node '{node_name}'")
        return await dispatcher.dispatch(request)


def build_cluster_chat_host_from_remote_config(
    *,
    repo_root: str,
    session_root: str,
    remote_config_path: str,
    env: Mapping[str, str] | None = None,
) -> tuple[OpenAgenticOptions, FileSessionStore, dict[str, Any]]:
    bootstrap = load_remote_cluster_bootstrap(repo_root=repo_root, config_path=remote_config_path, env=env)
    session_store = FileSessionStore(root_dir=Path(session_root))
    provider = bootstrap.host_provider or UnavailableRemoteProvider()
    health_status = {
        "deployment_mode": "real-model",
        "provider_ready": bootstrap.self_check.provider_ready,
        "provider_profiles": list(bootstrap.provider_profiles),
        "config_source": bootstrap.config_source,
    }
    if bootstrap.self_check.errors:
        health_status["provider_errors"] = list(bootstrap.self_check.errors)
    options = OpenAgenticOptions(
        provider=provider,
        model=bootstrap.host_model or "gpt-5.2",
        api_key=bootstrap.host_provider_spec.api_key if bootstrap.host_provider_spec is not None else None,
        cwd=repo_root,
        project_dir=repo_root,
        tools=default_tool_registry(),
        permission_gate=PermissionGate(permission_mode="bypass"),
        session_store=session_store,
        setting_sources=["project"],
        agents=bootstrap.agents,
    )
    return options, session_store, health_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cluster-hosted chat bridge server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--session-root", required=True)
    parser.add_argument("--provider-factory", default="")
    parser.add_argument("--remote-config", default="")
    parser.add_argument("--agents-factory", default="")
    parser.add_argument("--model", default="fake")
    parser.add_argument("--host-node-name", default="")
    parser.add_argument("--host-node-name-env", default="")
    parser.add_argument("--node-url", action="append", default=[])
    parser.add_argument("--sync-mirror", action="append", default=[])
    args = parser.parse_args(argv)

    host_node_name = args.host_node_name or (os.environ.get(args.host_node_name_env, "") if args.host_node_name_env else "")
    node_urls = _parse_node_urls(args.node_url)
    health_status: dict[str, Any] = {}

    if args.remote_config:
        options, session_store, health_status = build_cluster_chat_host_from_remote_config(
            repo_root=args.repo_root,
            session_root=args.session_root,
            remote_config_path=args.remote_config,
            env=os.environ,
        )
    else:
        if not args.provider_factory:
            raise SystemExit("cluster chat host requires --provider-factory or --remote-config")
        provider = _load_factory(args.provider_factory)()
        agents = _load_factory(args.agents_factory)() if args.agents_factory else {}
        session_store = FileSessionStore(root_dir=Path(args.session_root))
        options = OpenAgenticOptions(
            provider=provider,
            model=args.model,
            cwd=args.repo_root,
            project_dir=args.repo_root,
            tools=default_tool_registry(),
            permission_gate=PermissionGate(permission_mode="bypass"),
            session_store=session_store,
            agents=agents if isinstance(agents, Mapping) else {},
        )

    dispatcher = StaticNodeHttpRemoteTaskDispatcher(node_urls=node_urls) if node_urls else None
    options = replace(options, remote_task_dispatcher=dispatcher)
    synchronizer = CommittedGitSynchronizer(
        authoritative_cwd=args.repo_root,
        mirror_cwds=tuple(args.sync_mirror),
    )
    httpd = ClusterChatHostServer(
        base_options=options,
        session_store=session_store,
        host=args.host,
        port=args.port,
        host_node_name=host_node_name or None,
        git_synchronizer=synchronizer,
        health_status=health_status,
    ).make_server()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        httpd.server_close()
    return 0


def _load_factory(spec: str):
    module_name, sep, attr_name = spec.partition(":")
    if not module_name or not sep or not attr_name:
        raise SystemExit("factory spec must look like package.module:callable")
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name, None)
    if factory is None or not callable(factory):
        raise SystemExit(f"factory not found: {spec}")
    return factory


def _parse_node_urls(raw_items: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in raw_items:
        node_name, sep, url = str(raw or "").partition("=")
        node_name = node_name.strip()
        url = url.strip()
        if not node_name or not sep or not url:
            raise SystemExit("--node-url entries must look like node-name=http://host:port")
        mapping[node_name] = url
    return mapping


if __name__ == "__main__":
    raise SystemExit(main())
