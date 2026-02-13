from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from ..auth import OAuthAuth, all_auth
from ..opencode_config import load_merged_config
from ..options import OpenAgenticOptions
from ..providers.catalog import build_provider_listing
from ..serialization import event_to_dict
from ..sessions.rebuild import rebuild_messages
from ..sessions.store import FileSessionStore
from ..sessions.todos import normalize_todos_for_api
from ..share.local import LocalShareProvider
from ..share.share import fetch_shared_session, share_session, unshare_session
from .opencode_view import build_message_v2

_DEFAULT_MAX_REQUEST_BYTES = 2_000_000


class _PromptQueues:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_permissions: dict[str, dict[str, Any]] = {}
        self._permission_answers: dict[str, queue.Queue[str]] = {}
        self._pending_questions: dict[str, dict[str, Any]] = {}
        self._question_answers: dict[str, queue.Queue[list[str]]] = {}

    def list_permissions(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._pending_permissions.values())

    def create_permission(self, request_id: str, rec: dict[str, Any]) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._pending_permissions[request_id] = dict(rec)
            self._permission_answers[request_id] = q
        return q

    def remove_permission(self, request_id: str) -> None:
        with self._lock:
            self._pending_permissions.pop(request_id, None)
            self._permission_answers.pop(request_id, None)

    def submit_permission_reply(self, request_id: str, reply: str) -> bool:
        with self._lock:
            q = self._permission_answers.get(request_id)
        if q is None:
            return False
        q.put_nowait(reply)
        return True

    def list_questions(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._pending_questions.values())

    def create_question(self, request_id: str, rec: dict[str, Any]) -> queue.Queue[list[str]]:
        q: queue.Queue[list[str]] = queue.Queue()
        with self._lock:
            self._pending_questions[request_id] = dict(rec)
            self._question_answers[request_id] = q
        return q

    def remove_question(self, request_id: str) -> None:
        with self._lock:
            self._pending_questions.pop(request_id, None)
            self._question_answers.pop(request_id, None)

    def submit_question_reply(self, request_id: str, answers: list[str]) -> bool:
        with self._lock:
            q = self._question_answers.get(request_id)
        if q is None:
            return False
        q.put_nowait(list(answers))
        return True


def _parse_request_target(path: str) -> tuple[list[str], dict[str, str]]:
    u = urlparse(path or "")
    parts = [p for p in (u.path or "").split("/") if p]
    qs = parse_qs(u.query or "")
    query: dict[str, str] = {}
    for k, v in qs.items():
        if not v:
            continue
        query[str(k)] = str(v[0])
    return parts, query


def _in_tree(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except AttributeError:  # pragma: no cover
        ap = os.path.normcase(os.fspath(path.resolve()))
        bp = os.path.normcase(os.fspath(root.resolve()))
        return os.path.commonpath([ap, bp]) == bp


def _safe_fs_path(*, root: Path, raw: str) -> Path | None:
    s = str(raw or "").strip()
    if not s:
        return root
    p = Path(s)
    if p.is_absolute():
        return None
    full = (root / p).resolve()
    if not _in_tree(full, root):
        return None
    return full


def _decode_basic(authz: str) -> tuple[str, str] | None:
    s = str(authz or "").strip()
    if not s.lower().startswith("basic "):
        return None
    b64 = s.split(" ", 1)[1].strip()
    try:
        raw = base64.b64decode(b64.encode("ascii"), validate=True).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    if ":" not in raw:
        return None
    user, pw = raw.split(":", 1)
    return user, pw


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    # OpenCode parity: optional Basic auth gate.
    pw = (os.environ.get("OPENCODE_SERVER_PASSWORD") or "").strip()
    user = (os.environ.get("OPENCODE_SERVER_USERNAME") or "opencode").strip() or "opencode"
    bearer = (os.environ.get("OA_SERVER_TOKEN") or "").strip()
    if not pw and not bearer:
        return True

    authz = handler.headers.get("Authorization") or ""
    if bearer and authz.strip().lower() == f"bearer {bearer}".lower():
        return True
    if pw:
        tup = _decode_basic(authz)
        if tup is not None and tup[0] == user and tup[1] == pw:
            return True
    return False


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    max_bytes = int(getattr(handler.server, "max_request_bytes", _DEFAULT_MAX_REQUEST_BYTES) or _DEFAULT_MAX_REQUEST_BYTES)
    if length > max_bytes:
        raise ValueError("payload_too_large")
    raw = handler.rfile.read(length)
    try:
        obj = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        _ = e
        raise ValueError("invalid_json") from e
    return obj if isinstance(obj, dict) else {}


def _write_json(handler: BaseHTTPRequestHandler, status: int, obj: Any) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json_or_write_error(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    try:
        return _read_json(handler)
    except ValueError as e:
        msg = str(e)
        if msg == "payload_too_large":
            _write_json(handler, 413, {"error": "payload_too_large"})
            return None
        if msg == "invalid_json":
            _write_json(handler, 400, {"error": "invalid_json"})
            return None
        _write_json(handler, 400, {"error": "invalid_request"})
        return None


def _write_text(handler: BaseHTTPRequestHandler, status: int, text: str, *, content_type: str = "text/plain; charset=utf-8") -> None:
    raw = (text or "").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _session_info(store: FileSessionStore, session_id: str) -> dict[str, Any] | None:
    try:
        _ = store.session_dir(session_id)
    except Exception:
        return None
    rec = store.read_meta_record(session_id)
    if not rec:
        return None
    created = rec.get("created_at")
    created_ts: float | None = None
    if isinstance(created, (int, float)):
        created_ts = float(created)
    md = rec.get("metadata")
    md2: dict[str, Any] = dict(md) if isinstance(md, dict) else {}
    title = md2.get("title")
    title2 = str(title) if isinstance(title, str) else ""
    time_obj = md2.get("time")
    archived = None
    if isinstance(time_obj, dict):
        archived_raw = time_obj.get("archived")
        if isinstance(archived_raw, float):
            archived = archived_raw
        elif isinstance(archived_raw, int):
            archived = float(archived_raw)
    return {
        "id": session_id,
        "title": title2,
        "time": {
            "created": created_ts,
            **({"archived": archived} if archived is not None else {}),
        },
        "metadata": md2,
    }


@dataclass(frozen=True, slots=True)
class OpenAgenticHttpServer:
    options: OpenAgenticOptions
    host: str = "127.0.0.1"
    port: int = 0

    def serve_forever(self) -> ThreadingHTTPServer:
        store = self.options.session_store
        if store is None:
            root = self.options.session_root or Path.home() / ".openagentic-sdk"
            store = FileSessionStore(root_dir=root)

        opts = self.options

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

        hub = _EventHub()

        running_abort: dict[str, threading.Event] = {}
        running_lock = threading.Lock()

        # VSCode extension parity endpoints use a "current" session.
        tui_active_session_id: str | None = None
        tui_lock = threading.Lock()

        # Permission / Question queues (OpenCode parity endpoints).
        prompt_queues = _PromptQueues()

        def _make_permission_gate_for_server():
            # Build a PermissionGate that routes approvals + AskUserQuestion answers
            # through in-memory queues exposed by /permission and /question.
            import uuid

            from ..permissions.gate import PermissionGate
            from ..permissions.gate import UserQuestion as GateUserQuestion

            async def _user_answerer(q: GateUserQuestion) -> str:
                qid = str(getattr(q, "question_id", "") or uuid.uuid4().hex)
                rec = {
                    "id": qid,
                    "question_id": qid,
                    "prompt": str(getattr(q, "prompt", "")),
                    "choices": list(getattr(q, "choices", []) or []),
                }
                q_queue = prompt_queues.create_question(qid, rec)
                try:
                    ans = q_queue.get(timeout=300.0)
                finally:
                    prompt_queues.remove_question(qid)
                return ans[0] if ans else ""

            async def _approver(tool_name: str, tool_input: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
                # These tools are safe/UX-only and should not require explicit approval.
                if tool_name in {"Read", "Glob", "Grep", "Skill", "SlashCommand", "AskUserQuestion", "TodoWrite"}:
                    return True

                rid = str(context.get("tool_use_id") or "") or uuid.uuid4().hex
                rec = {
                    "id": rid,
                    "requestID": rid,
                    "tool": tool_name,
                    "input": dict(tool_input),
                    "message": None,
                }
                q_queue = prompt_queues.create_permission(rid, rec)
                try:
                    reply = q_queue.get(timeout=300.0)
                finally:
                    prompt_queues.remove_permission(rid)
                return str(reply).strip().lower() in ("allow", "yes", "y")

            return PermissionGate(
                permission_mode="callback",
                approver=_approver,
                interactive=False,
                user_answerer=_user_answerer,
            )

        def _start_prompt_async(*, sid: str, prompt: str) -> None:
            # Shared helper for /session/{id}/prompt_async and /tui/append-prompt.
            abort_ev = threading.Event()
            with running_lock:
                running_abort[sid] = abort_ev

            def _bg() -> None:
                try:
                    async def _run_bg() -> None:
                        from ..api import query as query_events

                        gate2 = _make_permission_gate_for_server()
                        opts2 = replace(opts, resume=sid, session_store=store, abort_event=abort_ev, permission_gate=gate2)
                        async for ev in query_events(prompt=prompt, options=opts2):
                            d = event_to_dict(ev)
                            hub.publish({"type": "session.event", "session_id": sid, "event": d})

                    asyncio.run(_run_bg())
                finally:
                    with running_lock:
                        running_abort.pop(sid, None)

            threading.Thread(target=_bg, name=f"oa-session-{sid}", daemon=True).start()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if not _authorized(self):
                    _write_json(self, 401, {"error": "unauthorized"})
                    return

                parts, query = _parse_request_target(self.path)

                # Non-OpenCode convenience.
                if parts == ["health"]:
                    _write_json(self, 200, {"ok": True})
                    return

                # OpenCode parity.
                if parts == ["global", "health"]:
                    _write_json(self, 200, {"healthy": True, "version": "openagentic-sdk"})
                    return

                if parts == ["app"]:
                    # OpenCode parity: VSCode extension probes this route.
                    _write_text(
                        self,
                        200,
                        """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>openagentic-sdk</title>
  </head>
  <body>
    <h1>openagentic-sdk</h1>
    <p>This is a minimal compatibility endpoint for the OpenCode VSCode extension.</p>
  </body>
</html>
""",
                        content_type="text/html; charset=utf-8",
                    )
                    return

                if parts == ["path"]:
                    cfg_dir = os.environ.get("OPENCODE_CONFIG_DIR")
                    _write_json(
                        self,
                        200,
                        {
                            "home": str(Path.home()),
                            "state": str(store.root_dir),
                            "config": str(Path(cfg_dir).resolve()) if isinstance(cfg_dir, str) and cfg_dir else "",
                            "worktree": str(Path(opts.project_dir or opts.cwd).resolve()),
                            "directory": str(Path(opts.cwd).resolve()),
                        },
                    )
                    return

                if parts == ["doc"]:
                    # Minimal OpenAPI-like doc endpoint (OpenCode has interactive /doc).
                    _write_json(
                        self,
                        200,
                        {
                            "openapi": "3.1.1",
                            "info": {"title": "openagentic-sdk", "version": "0.1.4"},
                             "paths": {
                                 "/global/health": {"get": {}},
                                 "/app": {"get": {}},
                                 "/global/event": {"get": {}},
                                 "/event": {"get": {}},
                                 "/tui/append-prompt": {"post": {}},
                                 "/provider": {"get": {}},
                                "/provider/auth": {"get": {}},
                                "/provider/{providerID}/oauth/authorize": {"post": {}},
                                "/provider/{providerID}/oauth/callback": {"post": {}},
                                "/session": {"get": {}, "post": {}},
                                "/session/status": {"get": {}},
                                "/session/{id}": {"get": {}, "patch": {}, "delete": {}},
                                "/session/{id}/message": {"get": {}, "post": {}},
                                "/session/{id}/children": {"get": {}},
                                "/session/{id}/todo": {"get": {}},
                                "/session/{id}/transcript": {"get": {}},
                                "/session/{id}/fork": {"post": {}},
                                "/session/{id}/prompt_async": {"post": {}},
                                "/session/{id}/abort": {"post": {}},
                                "/permission": {"get": {}},
                                "/permission/{id}/reply": {"post": {}},
                                "/question": {"get": {}},
                                "/question/{id}/reply": {"post": {}},
                                "/question/{id}/reject": {"post": {}},
                                "/find": {"get": {}},
                                "/find/file": {"get": {}},
                                "/file": {"get": {}},
                                "/file/content": {"get": {}},
                                "/file/status": {"get": {}},
                            },
                        },
                    )
                    return

                if parts == ["provider"]:
                    # OpenCode parity: provider list surface (models.dev + config + auth).
                    try:
                        cfg = load_merged_config(cwd=str(Path(opts.project_dir or opts.cwd)))
                    except Exception:
                        cfg = {}
                    _write_json(self, 200, build_provider_listing(cfg if isinstance(cfg, dict) else None))
                    return

                if parts == ["provider", "auth"]:
                    # OpenCode parity: provider auth methods. OpenCode gathers
                    # these from plugins; we provide best-effort built-ins.
                    try:
                        cfg = load_merged_config(cwd=str(Path(opts.project_dir or opts.cwd)))
                    except Exception:
                        cfg = {}
                    auth = all_auth()

                    listing = build_provider_listing(cfg if isinstance(cfg, dict) else None)
                    auth_methods: dict[str, list[dict[str, str]]] = {}
                    all_list = listing.get("all")
                    providers: list[Any] = all_list if isinstance(all_list, list) else []
                    for p in providers:
                        pid = p.get("id") if isinstance(p, dict) else None
                        if not isinstance(pid, str) or not pid:
                            continue
                        methods: list[dict[str, str]] = [{"type": "api", "label": "API Key"}]
                        a = auth.get(pid)
                        if isinstance(a, OAuthAuth):
                            methods.append({"type": "oauth", "label": "OAuth"})
                        auth_methods[pid] = methods

                    _write_json(self, 200, auth_methods)
                    return

                if parts == ["event"]:
                    # SSE bus (best-effort, loopback-friendly).
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()

                    q = hub.subscribe()
                    try:
                        self.wfile.write(b"data: {\"type\":\"server.connected\"}\n\n")
                        self.wfile.flush()
                        last_hb = time.time()
                        while True:
                            try:
                                obj = q.get(timeout=0.5)
                                payload = json.dumps(obj, ensure_ascii=False)
                                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                                self.wfile.flush()
                            except queue.Empty:
                                pass
                            if time.time() - last_hb >= 30.0:
                                self.wfile.write(b"data: {\"type\":\"server.heartbeat\"}\n\n")
                                self.wfile.flush()
                                last_hb = time.time()
                    except Exception:
                        return
                    finally:
                        hub.unsubscribe(q)

                if parts == ["global", "event"]:
                    # OpenCode parity: global SSE wraps payload with directory.
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()

                    q = hub.subscribe()
                    directory = str(Path(opts.cwd).resolve())
                    try:
                        first = {"directory": directory, "payload": {"type": "server.connected"}}
                        self.wfile.write(f"data: {json.dumps(first, ensure_ascii=False)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        last_hb = time.time()
                        while True:
                            try:
                                obj = q.get(timeout=0.5)
                                wrapped = {"directory": directory, "payload": obj}
                                self.wfile.write(f"data: {json.dumps(wrapped, ensure_ascii=False)}\n\n".encode("utf-8"))
                                self.wfile.flush()
                            except queue.Empty:
                                pass
                            if time.time() - last_hb >= 30.0:
                                hb = {"directory": directory, "payload": {"type": "server.heartbeat"}}
                                self.wfile.write(f"data: {json.dumps(hb, ensure_ascii=False)}\n\n".encode("utf-8"))
                                self.wfile.flush()
                                last_hb = time.time()
                    except Exception:
                        return
                    finally:
                        hub.unsubscribe(q)

                if parts == ["find"]:
                    pattern = query.get("pattern")
                    if not isinstance(pattern, str) or not pattern.strip():
                        _write_json(self, 400, {"error": "invalid_pattern"})
                        return
                    root_dir = Path(opts.cwd).resolve()
                    # Prefer rg for speed.
                    matches: list[dict[str, Any]] = []
                    if shutil.which("rg"):
                        try:
                            res = subprocess.run(
                                ["rg", "--json", "-m", "10", pattern, os.fspath(root_dir)],
                                check=False,
                                capture_output=True,
                                text=True,
                                timeout=5.0,
                            )
                            for line in (res.stdout or "").splitlines():
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                if not isinstance(obj, dict) or obj.get("type") != "match":
                                    continue
                                data_obj = obj.get("data")
                                if not isinstance(data_obj, dict):
                                    continue
                                path_obj = data_obj.get("path")
                                path_text = None
                                if isinstance(path_obj, dict):
                                    path_text = path_obj.get("text")
                                line_no = None
                                lines = data_obj.get("lines")
                                ln_raw = data_obj.get("line_number")
                                if isinstance(ln_raw, int):
                                    line_no = ln_raw
                                text0 = None
                                if isinstance(lines, dict) and isinstance(lines.get("text"), str):
                                    text0 = lines.get("text")
                                if isinstance(path_text, str):
                                    matches.append({"path": path_text, "line": line_no, "text": text0})
                                if len(matches) >= 10:
                                    break
                        except Exception:
                            matches = []
                    _write_json(self, 200, matches)
                    return

                if parts == ["find", "file"]:
                    q = query.get("query")
                    if not isinstance(q, str) or not q.strip():
                        _write_json(self, 400, {"error": "invalid_query"})
                        return
                    root_dir = Path(opts.cwd).resolve()
                    try:
                        limit = int(query.get("limit") or "200")
                    except Exception:
                        limit = 200
                    limit = max(1, min(200, limit))
                    paths_out: list[str] = []
                    needle = q.strip().lower()
                    for p in root_dir.rglob("*"):
                        if len(paths_out) >= limit:
                            break
                        try:
                            rel = p.relative_to(root_dir)
                        except Exception:
                            continue
                        if needle in rel.as_posix().lower():
                            paths_out.append(rel.as_posix())
                    _write_json(self, 200, paths_out)
                    return

                if parts == ["file"]:
                    raw = query.get("path") or ""
                    root_dir = Path(opts.cwd).resolve()
                    p = _safe_fs_path(root=root_dir, raw=str(raw))
                    if p is None or not p.exists() or not p.is_dir():
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    nodes: list[dict[str, Any]] = []
                    for child in sorted(p.iterdir(), key=lambda x: x.name):
                        rel = child.relative_to(root_dir).as_posix()
                        nodes.append({"path": rel, "name": child.name, "type": "directory" if child.is_dir() else "file"})
                    _write_json(self, 200, nodes)
                    return

                if parts == ["file", "content"]:
                    raw = query.get("path") or ""
                    root_dir = Path(opts.cwd).resolve()
                    p = _safe_fs_path(root=root_dir, raw=str(raw))
                    if p is None or not p.exists() or not p.is_file():
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    data_bytes = p.read_bytes()
                    if len(data_bytes) > 1024 * 1024:
                        data_bytes = data_bytes[: 1024 * 1024]
                    text = data_bytes.decode("utf-8", errors="replace")
                    _write_json(self, 200, {"path": str(raw), "content": text})
                    return

                if parts == ["file", "status"]:
                    root_dir = Path(opts.cwd).resolve()
                    # Best-effort git porcelain.
                    if shutil.which("git") is None:
                        _write_json(self, 200, [])
                        return
                    try:
                        res = subprocess.run(
                            ["git", "-C", os.fspath(root_dir), "status", "--porcelain"],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=5.0,
                        )
                        status_out: list[dict[str, Any]] = []
                        for ln in (res.stdout or "").splitlines():
                            if len(ln) < 4:
                                continue
                            status_out.append({"status": ln[:2], "path": ln[3:]})
                        _write_json(self, 200, status_out)
                        return
                    except Exception:
                        _write_json(self, 200, [])
                        return

                if parts == ["permission"]:
                    _write_json(self, 200, prompt_queues.list_permissions())
                    return

                if parts == ["question"]:
                    _write_json(self, 200, prompt_queues.list_questions())
                    return

                if len(parts) == 2 and parts[0] == "share":
                    share_id = parts[1]
                    try:
                        provider2 = LocalShareProvider(root_dir=store.root_dir / "shares")
                        ss = fetch_shared_session(share_id=share_id, provider=provider2)
                    except Exception:
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    _write_json(self, 200, ss.payload)
                    return

                if parts == ["session"]:
                    # OpenCode-like: return an array.
                    sessions = list_sessions(store)
                    limit_raw = query.get("limit")
                    try:
                        limit = int(limit_raw) if isinstance(limit_raw, str) and limit_raw else None
                    except Exception:
                        limit = None
                    sessions_out = sessions
                    if isinstance(limit, int) and limit > 0:
                        sessions_out = sessions_out[:limit]
                    _write_json(self, 200, sessions_out)
                    return

                if parts == ["session", "status"]:
                    data: dict[str, Any] = {}
                    with running_lock:
                        busy = set(running_abort.keys())
                    for s in list_sessions(store):
                        sid = s.get("id")
                        if isinstance(sid, str) and sid:
                            data[sid] = {"type": "busy" if sid in busy else "idle"}
                    _write_json(self, 200, data)
                    return

                if len(parts) >= 2 and parts[0] == "session":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    if len(parts) == 2:
                        info = _session_info(store, sid)
                        if info is None:
                            _write_json(self, 404, {"error": "not_found"})
                            return
                        _write_json(self, 200, info)
                        return

                    if len(parts) == 3 and parts[2] == "events":
                        # Debug endpoint (non-OpenCode).
                        evs = store.read_events(sid)
                        _write_json(self, 200, {"session_id": sid, "events": [event_to_dict(e) for e in evs]})
                        return

                    if len(parts) == 3 and parts[2] == "model_messages":
                        # Debug endpoint (non-OpenCode): provider-history rebuild.
                        evs = store.read_events(sid)
                        msgs = rebuild_messages(evs, max_events=1000, max_bytes=2_000_000)
                        _write_json(self, 200, {"session_id": sid, "messages": msgs})
                        return

                    if len(parts) == 3 and parts[2] == "message":
                        evs = store.read_events(sid)
                        msgs = build_message_v2(evs, session_id=sid)
                        _write_json(self, 200, msgs)
                        return

                    if len(parts) == 3 and parts[2] == "children":
                        if not store.read_meta_record(sid):
                            _write_json(self, 404, {"error": "not_found"})
                            return
                        kids: list[dict[str, Any]] = []
                        for info in list_sessions(store):
                            md = info.get("metadata") if isinstance(info, dict) else None
                            if isinstance(md, dict) and md.get("parent_session_id") == sid:
                                kids.append(info)
                        _write_json(self, 200, kids)
                        return

                    if len(parts) == 3 and parts[2] == "todo":
                        p = store.session_dir(sid) / "todos.json"
                        if not p.exists():
                            _write_json(self, 200, [])
                            return
                        try:
                            obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                        except Exception:  # noqa: BLE001
                            _write_json(self, 200, [])
                            return
                        todos_raw = obj.get("todos") if isinstance(obj, dict) else None
                        _write_json(self, 200, normalize_todos_for_api(todos_raw))
                        return

                    if len(parts) == 3 and parts[2] == "transcript":
                        p = store.session_dir(sid) / "transcript.jsonl"
                        if not p.exists():
                            _write_json(self, 200, {"session_id": sid, "entries": []})
                            return
                        entries: list[dict[str, Any]] = []
                        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            if isinstance(obj, dict):
                                entries.append(obj)
                        _write_json(self, 200, {"session_id": sid, "entries": entries})
                        return

                    if len(parts) == 4 and parts[2] == "message":
                        mid = parts[3]
                        evs = store.read_events(sid)
                        msgs = build_message_v2(evs, session_id=sid)
                        for m in msgs:
                            info = m.get("info") if isinstance(m, dict) else None
                            if isinstance(info, dict) and info.get("id") == mid:
                                _write_json(self, 200, m)
                                return
                        _write_json(self, 404, {"error": "not_found"})
                        return

                _write_json(self, 404, {"error": "not_found"})

            def do_POST(self):  # noqa: N802
                nonlocal tui_active_session_id
                if not _authorized(self):
                    _write_json(self, 401, {"error": "unauthorized"})
                    return

                parts, _query = _parse_request_target(self.path)

                # OpenCode parity: provider OAuth endpoints (stub until full
                # provider OAuth manager is implemented).
                if len(parts) == 4 and parts[0] == "provider" and parts[2] == "oauth" and parts[3] in ("authorize", "callback"):
                    _write_json(self, 400, {"error": "unsupported"})
                    return

                # OpenCode parity: VSCode extension "append prompt" bridge.
                if parts == ["tui", "append-prompt"]:
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    prompt = body.get("text") or body.get("prompt") or body.get("content")
                    if not isinstance(prompt, str) or not prompt:
                        _write_json(self, 400, {"error": "invalid_prompt"})
                        return

                    sid_raw = body.get("session_id") or body.get("sessionId")
                    sid: str | None = str(sid_raw) if isinstance(sid_raw, str) and sid_raw else None
                    if sid is not None:
                        try:
                            _ = store.session_dir(sid)
                        except ValueError:
                            _write_json(self, 400, {"error": "invalid_session_id"})
                            return
                    else:
                        with tui_lock:
                            sid = tui_active_session_id
                        if sid is not None and store.read_meta_record(sid):
                            pass
                        else:
                            sid = store.create_session(metadata={"title": "VSCode"})
                            with tui_lock:
                                tui_active_session_id = sid

                    _start_prompt_async(sid=sid, prompt=prompt)
                    _write_json(self, 200, {"ok": True, "session_id": sid})
                    return

                # OpenCode parity: permission and question queues.
                if len(parts) == 3 and parts[0] == "permission" and parts[2] == "reply":
                    request_id = parts[1]
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    reply = body.get("reply")
                    if not isinstance(reply, str) or not reply:
                        _write_json(self, 400, {"error": "invalid_reply"})
                        return
                    if not prompt_queues.submit_permission_reply(request_id, reply):
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    _write_json(self, 200, True)
                    return

                if len(parts) == 3 and parts[0] == "question" and parts[2] == "reply":
                    request_id = parts[1]
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    answers = body.get("answers")
                    if isinstance(answers, str):
                        answers_list = [answers]
                    elif isinstance(answers, list):
                        answers_list = [str(x) for x in answers if isinstance(x, str) and x]
                    else:
                        answers_list = []
                    if not prompt_queues.submit_question_reply(request_id, answers_list):
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    _write_json(self, 200, True)
                    return

                if len(parts) == 3 and parts[0] == "question" and parts[2] == "reject":
                    request_id = parts[1]
                    if not prompt_queues.submit_question_reply(request_id, []):
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    _write_json(self, 200, True)
                    return
                if parts == ["session"]:
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    md_raw = body.get("metadata")
                    md: dict[str, Any] = {}
                    if isinstance(md_raw, dict):
                        for k, v in md_raw.items():
                            md[str(k)] = v
                    title = body.get("title")
                    if isinstance(title, str) and title.strip():
                        md["title"] = title.strip()
                    sid = store.create_session(metadata=md)
                    info = _session_info(store, sid) or {"id": sid}
                    _write_json(self, 200, info)
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "message":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    prompt = body.get("prompt") or body.get("content") or body.get("text")
                    if not isinstance(prompt, str) or not prompt:
                        _write_json(self, 400, {"error": "invalid_prompt"})
                        return

                    abort_ev = threading.Event()
                    with running_lock:
                        running_abort[sid] = abort_ev

                    async def _run_and_publish() -> tuple[str, str]:
                        from ..api import query as query_events

                        gate2 = _make_permission_gate_for_server()
                        opts2 = replace(opts, resume=sid, session_store=store, abort_event=abort_ev, permission_gate=gate2)
                        last_assistant = ""
                        async for ev in query_events(prompt=prompt, options=opts2):
                            d = event_to_dict(ev)
                            hub.publish({"type": "session.event", "session_id": sid, "event": d})
                            if d.get("type") == "assistant.message":
                                last_assistant = str(d.get("text") or "")
                        return sid, last_assistant

                    try:
                        sid2, _last = asyncio.run(_run_and_publish())
                    finally:
                        with running_lock:
                            running_abort.pop(sid, None)

                    # Return the latest assistant message in the OpenCode-like view.
                    evs2 = store.read_events(sid2)
                    msgs = build_message_v2(evs2, session_id=sid2)
                    latest = None
                    for m in reversed(msgs):
                        info = m.get("info") if isinstance(m, dict) else None
                        if isinstance(info, dict) and info.get("role") == "assistant":
                            latest = m
                            break
                    _write_json(self, 200, latest or {"info": {"role": "assistant"}, "parts": []})
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "fork":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    if not store.read_meta_record(sid):
                        _write_json(self, 404, {"error": "not_found"})
                        return

                    # OpenCode parity: do not fork a busy session.
                    with running_lock:
                        if sid in running_abort:
                            _write_json(self, 409, {"error": "busy"})
                            return
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return

                    head_seq: int | None = None
                    msg_id = body.get("messageID") or body.get("messageId")
                    if isinstance(msg_id, str) and "_" in msg_id:
                        try:
                            msg_seq = int(msg_id.rsplit("_", 1)[1])
                        except Exception:
                            msg_seq = 0
                        if msg_seq > 1:
                            # OpenCode fork excludes the message at messageID and beyond.
                            head_seq = msg_seq - 1

                    try:
                        child = store.fork_session(sid, head_seq=head_seq)
                    except Exception:
                        _write_json(self, 400, {"error": "invalid_fork"})
                        return

                    info = _session_info(store, child)
                    _write_json(self, 200, info or {"id": child})
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "prompt_async":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    prompt = body.get("prompt") or body.get("content") or body.get("text")
                    if not isinstance(prompt, str) or not prompt:
                        _write_json(self, 400, {"error": "invalid_prompt"})
                        return

                    _start_prompt_async(sid=sid, prompt=prompt)
                    self.send_response(204)
                    self.end_headers()
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "abort":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    with running_lock:
                        ev = running_abort.get(sid)
                    if ev is not None:
                        ev.set()
                    _write_json(self, 200, True)
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "revert":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return

                    head_seq = body.get("head_seq")
                    if isinstance(head_seq, int) and head_seq > 0:
                        store.set_head(sid, head_seq=head_seq, reason="revert")
                        _write_json(self, 200, _session_info(store, sid) or {"id": sid})
                        return

                    msg_id = body.get("messageID") or body.get("messageId")
                    if isinstance(msg_id, str) and "_" in msg_id:
                        try:
                            seq = int(msg_id.rsplit("_", 1)[1])
                        except Exception:
                            seq = 0
                        if seq > 0:
                            store.set_head(sid, head_seq=seq, reason="revert")
                            _write_json(self, 200, _session_info(store, sid) or {"id": sid})
                            return

                    _write_json(self, 400, {"error": "invalid_revert"})
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "unrevert":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    store.undo(sid)
                    _write_json(self, 200, _session_info(store, sid) or {"id": sid})
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "share":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    # Create a share payload and store the share id in metadata.
                    provider2 = LocalShareProvider(root_dir=store.root_dir / "shares")
                    share_id = share_session(store=store, session_id=sid, provider=provider2)
                    store.update_metadata(sid, patch={"share_id": share_id, "shared": True})
                    _write_json(self, 200, _session_info(store, sid) or {"id": sid})
                    return

                _write_json(self, 404, {"error": "not_found"})

            def do_PATCH(self):  # noqa: N802
                if not _authorized(self):
                    _write_json(self, 401, {"error": "unauthorized"})
                    return
                parts, _query = _parse_request_target(self.path)
                if len(parts) == 2 and parts[0] == "session":
                    sid = parts[1]
                    body = _read_json_or_write_error(self)
                    if body is None:
                        return
                    patch: dict[str, Any] = {}
                    title = body.get("title")
                    if isinstance(title, str):
                        patch["title"] = title
                    t = body.get("time")
                    if isinstance(t, dict):
                        archived = t.get("archived")
                        if isinstance(archived, (int, float)):
                            patch["time"] = {"archived": float(archived)}
                    try:
                        store.update_metadata(sid, patch=patch)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    except FileNotFoundError:
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    info = _session_info(store, sid)
                    _write_json(self, 200, info or {"id": sid})
                    return
                _write_json(self, 404, {"error": "not_found"})

            def do_DELETE(self):  # noqa: N802
                if not _authorized(self):
                    _write_json(self, 401, {"error": "unauthorized"})
                    return
                parts, _query = _parse_request_target(self.path)
                if len(parts) == 2 and parts[0] == "session":
                    sid = parts[1]
                    try:
                        store.delete_session(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    except FileNotFoundError:
                        _write_json(self, 404, {"error": "not_found"})
                        return
                    _write_json(self, 200, True)
                    return

                if len(parts) == 3 and parts[0] == "session" and parts[2] == "share":
                    sid = parts[1]
                    try:
                        _ = store.session_dir(sid)
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    md = store.read_metadata(sid)
                    share_id = md.get("share_id")
                    if isinstance(share_id, str) and share_id:
                        provider2 = LocalShareProvider(root_dir=store.root_dir / "shares")
                        unshare_session(share_id=share_id, provider=provider2)
                    # Clear metadata.
                    store.update_metadata(sid, patch={"share_id": None, "shared": False})
                    _write_json(self, 200, _session_info(store, sid) or {"id": sid})
                    return
                _write_json(self, 404, {"error": "not_found"})

            def log_message(self, format, *args):  # noqa: A002,ANN001
                return

        httpd = ThreadingHTTPServer((self.host, int(self.port)), Handler)
        setattr(httpd, "max_request_bytes", _DEFAULT_MAX_REQUEST_BYTES)
        return httpd


def list_sessions(store: FileSessionStore) -> list[dict[str, Any]]:
    root = store.root_dir / "sessions"
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        meta = d / "meta.json"
        if not meta.exists():
            continue
        try:
            obj = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(obj, dict):
            continue
        sid = obj.get("session_id")
        if isinstance(sid, str) and sid:
            info = _session_info(store, sid)
            if info is not None:
                out.append(info)
    return out


def serve_http(*, options: OpenAgenticOptions, host: str = "127.0.0.1", port: int = 0) -> None:
    server = OpenAgenticHttpServer(options=options, host=host, port=port)
    httpd = server.serve_forever()
    httpd.serve_forever()
