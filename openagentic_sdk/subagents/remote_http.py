from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, AsyncIterator, Mapping
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from ..options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from ..remote_cluster_config import ResolvedRemoteProviderSpec, build_provider_from_spec
from ..serialization import event_to_dict
from ..server.session_transcript_view import build_session_transcript
from ..sessions.store import FileSessionStore
from .actor_lifecycle import ActorDownEvent, classify_remote_exception_down
from .actor_protocol import ActorEnvelope
from .actor_tracing import ActorTracing, actor_execution_attributes, down_trace_attributes, envelope_trace_attributes
from .remote_dispatch import resolve_git_head_only
from .remote_types import RemoteTaskDispatchHandle, RemoteTaskRequest
from .remote_worker import InProcessRemoteTaskWorker


@dataclass(slots=True)
class _ServerExecutionState:
    execution_id: str
    actor_id: str
    child_session_id: str
    target_node: str
    git_revision: str
    worker_execution_id: str | None
    handle: RemoteTaskDispatchHandle
    envelopes: list[ActorEnvelope] = field(default_factory=list)
    ack_heads: dict[str, int] = field(default_factory=dict)
    done: bool = False
    saw_down: bool = False
    close_requested: bool = False
    close_finalized: bool = False
    error: Exception | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)

    def append(self, envelope: ActorEnvelope) -> None:
        with self.condition:
            self.envelopes.append(envelope)
            if envelope.kind == "down":
                self.saw_down = True
            self.condition.notify_all()

    def mark_done(self, *, error: Exception | None = None) -> None:
        with self.condition:
            self.done = True
            self.error = error
            self.condition.notify_all()

    def record_ack(self, *, mailbox: str, acked_seq: int) -> None:
        with self.condition:
            current = self.ack_heads.get(mailbox, 0)
            if acked_seq > current:
                self.ack_heads[mailbox] = acked_seq

    def request_close(self) -> bool:
        with self.condition:
            already_requested = self.close_requested
            self.close_requested = True
            self.condition.notify_all()
            return not already_requested

    def begin_close_finalization(self) -> bool:
        with self.condition:
            if self.close_finalized:
                return False
            self.close_finalized = True
            return True


class HttpRemoteActorTransport:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 60.0,
        tracing: ActorTracing | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._tracing = tracing or ActorTracing(service_name="openagentic-sdk")

    async def spawn(self, request: RemoteTaskRequest) -> RemoteTaskDispatchHandle:
        transport_span = self._tracing.start_span(
            "oa.actor.transport",
            attributes=actor_execution_attributes(
                execution_id=request.worker_execution_id,
                actor_id=request.agent_name,
                agent_name=request.agent_name,
                dispatch_mode=request.definition.executor.kind,
                transport_kind="http",
                session_id=request.parent_session_id,
                parent_session_id=request.parent_session_id,
                target_node=request.definition.executor.node_name,
            ),
        )
        payload = _request_to_dict(request)
        try:
            response = await self._open_json_post(path="/dispatch", payload=payload)
            child_session_id = response.headers.get("X-OA-Child-Session-ID") or ""
            target_node = response.headers.get("X-OA-Target-Node") or ""
            git_revision = response.headers.get("X-OA-Git-Revision") or ""
            worker_execution_id = response.headers.get("X-OA-Execution-ID") or response.headers.get("X-OA-Worker-Execution-ID") or None
            if not child_session_id or not target_node or not git_revision:
                response.close()
                raise RuntimeError("Remote actor dispatch returned incomplete metadata headers")
            _disable_response_read_timeout(response)
            execution_id = worker_execution_id or child_session_id
            self._tracing.set_attributes(
                transport_span,
                actor_execution_attributes(
                    execution_id=execution_id,
                    actor_id=f"{request.agent_name}/{execution_id}",
                    agent_name=request.agent_name,
                    dispatch_mode=request.definition.executor.kind,
                    transport_kind="http",
                    session_id=request.parent_session_id,
                    parent_session_id=request.parent_session_id,
                    child_session_id=child_session_id,
                    target_node=target_node,
                ),
            )
            self._tracing.add_event(transport_span, "spawn", attributes={"oa.execution.id": execution_id})
            acked_heads: dict[str, int] = {}
            close_sent = False

            async def _envelopes():
                seen_message_ids: set[str] = set()
                current_response = response
                stalled_reconnects = 0
                while True:
                    saw_progress = False
                    try:
                        async for envelope in _read_envelopes_from_response(current_response):
                            if envelope.message_id in seen_message_ids:
                                continue
                            seen_message_ids.add(envelope.message_id)
                            saw_progress = True
                            self._tracing.add_event(transport_span, "receive", attributes=envelope_trace_attributes(envelope))
                            if envelope.kind == "down" and isinstance(envelope.payload, Mapping):
                                self._tracing.add_event(
                                    transport_span,
                                    "down",
                                    attributes=down_trace_attributes(ActorDownEvent.from_payload(envelope.payload)),
                                )
                            yield envelope
                            if envelope.kind == "down":
                                return
                    finally:
                        current_response.close()

                    stalled_reconnects = 0 if saw_progress else stalled_reconnects + 1
                    if stalled_reconnects > 2:
                        raise ConnectionError("remote actor stream ended without down")
                    self._tracing.add_event(
                        transport_span,
                        "replay",
                        attributes={
                            "oa.execution.id": execution_id,
                            "oa.mailbox": "child_events",
                            "oa.after.seq": acked_heads.get("child_events", 0),
                        },
                    )
                    current_response = await self._open_stream(
                        execution_id=execution_id,
                        mailbox="child_events",
                        after_seq=acked_heads.get("child_events", 0),
                    )

            async def _abort() -> None:
                self._tracing.add_event(transport_span, "abort", attributes={"oa.execution.id": execution_id})
                await self._open_json_post(
                    path="/abort",
                    payload={
                        "execution_id": execution_id,
                        "kind": "abort",
                    },
                    expect_json=False,
                )

            async def _send(envelope: ActorEnvelope) -> None:
                self._tracing.add_event(transport_span, "send", attributes=envelope_trace_attributes(envelope))
                await self._open_json_post(
                    path="/send",
                    payload=envelope.to_dict(),
                    expect_json=False,
                )

            async def _ack(envelope: ActorEnvelope) -> None:
                acked_seq = envelope.seq
                mailbox = envelope.mailbox
                if acked_heads.get(mailbox, 0) >= acked_seq:
                    return
                ack_envelope = ActorEnvelope(
                    protocol_version="v1",
                    message_id=uuid.uuid4().hex,
                    execution_id=execution_id,
                    sender_actor_id="host",
                    recipient_actor_id=envelope.sender_actor_id,
                    mailbox=mailbox,
                    seq=acked_seq,
                    kind="ack",
                    payload={"acked_seq": acked_seq, "mailbox": mailbox},
                    ts=asyncio.get_running_loop().time(),
                )
                await self._open_json_post(
                    path="/send",
                    payload=ack_envelope.to_dict(),
                    expect_json=False,
                )
                self._tracing.add_event(transport_span, "ack", attributes=envelope_trace_attributes(ack_envelope))
                acked_heads[mailbox] = acked_seq

            async def _close() -> None:
                nonlocal close_sent
                if close_sent:
                    return
                await self._open_json_post(
                    path="/close",
                    payload={
                        "execution_id": execution_id,
                        "kind": "close",
                    },
                    expect_json=False,
                )
                self._tracing.add_event(transport_span, "close", attributes={"oa.execution.id": execution_id})
                self._tracing.end_span(transport_span)
                close_sent = True

            return request.make_handle(
                child_session_id=child_session_id,
                target_node=target_node,
                git_revision=git_revision,
                worker_execution_id=worker_execution_id,
                envelopes=_envelopes(),
                sender=_send,
                acker=_ack,
                aborter=_abort,
                closer=_close,
            )
        except Exception:
            self._tracing.end_span(transport_span)
            raise

    def receive(self, handle: RemoteTaskDispatchHandle):
        if handle.envelopes is None:
            raise RuntimeError("remote actor handle does not expose actor envelopes")
        return handle.envelopes

    async def send(self, handle: RemoteTaskDispatchHandle, envelope: ActorEnvelope) -> None:
        await handle.send(envelope)

    async def abort(self, handle: RemoteTaskDispatchHandle) -> None:
        await handle.abort()

    async def close(self, handle: RemoteTaskDispatchHandle) -> None:
        await handle.close()

    async def _open_json_post(
        self,
        *,
        path: str,
        payload: Mapping[str, Any],
        expect_json: bool = False,
    ):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = urllib_request.Request(
            url=f"{self._base_url}{path}",
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return await asyncio.to_thread(urllib_request.urlopen, http_request, None, self._timeout_s)
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if expect_json:
                raise RuntimeError(f"Remote actor request failed with HTTP {exc.code}: {body}") from exc
            raise ConnectionError(f"Remote actor request failed with HTTP {exc.code}: {body}") from exc
        except urllib_error.URLError as exc:
            raise ConnectionError(f"Remote actor request failed: {exc.reason}") from exc

    async def _open_stream(self, *, execution_id: str, mailbox: str, after_seq: int):
        query = urllib_parse.urlencode(
            {
                "execution_id": execution_id,
                "mailbox": mailbox,
                "after_seq": str(after_seq),
            }
        )
        http_request = urllib_request.Request(
            url=f"{self._base_url}/stream?{query}",
            method="GET",
        )
        try:
            response = await asyncio.to_thread(urllib_request.urlopen, http_request, None, self._timeout_s)
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ConnectionError(f"Remote actor replay failed with HTTP {exc.code}: {body}") from exc
        except urllib_error.URLError as exc:
            raise ConnectionError(f"Remote actor replay failed: {exc.reason}") from exc
        _disable_response_read_timeout(response)
        return response


class HttpRemoteTaskDispatcher:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 60.0,
        tracing: ActorTracing | None = None,
    ) -> None:
        self._actor_transport = HttpRemoteActorTransport(base_url=base_url, timeout_s=timeout_s, tracing=tracing)

    def bind_actor_tracing(self, tracing: ActorTracing) -> None:
        self._actor_transport = HttpRemoteActorTransport(
            base_url=self._actor_transport._base_url,
            timeout_s=self._actor_transport._timeout_s,
            tracing=tracing,
        )

    async def dispatch(self, request: RemoteTaskRequest):
        return await self._actor_transport.spawn(request)


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
        session_store = self._session_store
        repo_root = self._repo_root
        node_name = self._node_name
        health_status = {"deployment_mode": "smoke", **dict(self._health_status)}
        execution_slots: threading.BoundedSemaphore | None = None
        execution_slot_limit: int | None = None
        execution_slots_lock = threading.Lock()
        execution_states: dict[str, _ServerExecutionState] = {}
        execution_states_lock = threading.Lock()

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

        def _lookup_state(execution_id: str) -> _ServerExecutionState | None:
            with execution_states_lock:
                return execution_states.get(execution_id)

        def _register_state(state: _ServerExecutionState) -> None:
            with execution_states_lock:
                execution_states[state.execution_id] = state

        def _unregister_state(execution_id: str) -> None:
            with execution_states_lock:
                execution_states.pop(execution_id, None)

        def _finalize_close(state: _ServerExecutionState) -> None:
            try:
                asyncio.run(state.handle.close())
            finally:
                _unregister_state(state.execution_id)

        def _start_execution(request: RemoteTaskRequest, *, slots: threading.BoundedSemaphore) -> _ServerExecutionState:
            handle = asyncio.run(worker.dispatch(request))
            execution_id = handle.execution_id or request.worker_execution_id or uuid.uuid4().hex
            actor_id = f"{request.agent_name}/{execution_id}"
            state = _ServerExecutionState(
                execution_id=execution_id,
                actor_id=actor_id,
                child_session_id=handle.child_session_id,
                target_node=handle.target_node,
                git_revision=handle.git_revision,
                worker_execution_id=handle.worker_execution_id,
                handle=handle,
            )
            _register_state(state)

            def _pump() -> None:
                error: Exception | None = None
                try:
                    asyncio.run(_consume_handle(request=request, state=state))
                except Exception as exc:  # noqa: BLE001
                    error = exc
                    if not state.saw_down:
                        down = classify_remote_exception_down(
                            execution_id=state.execution_id,
                            actor_id=state.actor_id,
                            dispatch_mode=request.definition.executor.kind,
                            exc=exc,
                            child_session_id=state.child_session_id,
                            target_node=state.target_node,
                            worker_execution_id=state.worker_execution_id,
                        )
                        state.append(_down_envelope_from_down(down=down, seq=len(state.envelopes) + 1))
                finally:
                    state.mark_done(error=error)
                    if state.close_requested and state.begin_close_finalization():
                        _finalize_close(state)
                    slots.release()

            threading.Thread(target=_pump, name=f"oa-remote-actor-{execution_id}", daemon=True).start()
            return state

        async def _consume_handle(*, request: RemoteTaskRequest, state: _ServerExecutionState) -> None:
            if state.handle.envelopes is not None:
                async for envelope in state.handle.envelopes:
                    state.append(envelope)
                return

            seq = 0
            async for event in state.handle.events:
                seq += 1
                state.append(
                    ActorEnvelope(
                        protocol_version="v1",
                        message_id=uuid.uuid4().hex,
                        execution_id=state.execution_id,
                        sender_actor_id=state.actor_id,
                        recipient_actor_id="host",
                        mailbox="child_events",
                        seq=seq,
                        kind="child_event",
                        payload={"event": event_to_dict(event)},
                        ts=asyncio.get_running_loop().time(),
                    )
                )

            if state.handle.down_future.done():
                down = state.handle.down_future.result()
                state.append(_down_envelope_from_down(down=down, seq=seq + 1))

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urllib_parse.urlparse(self.path)
                if parsed.path == "/health":
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
                    return
                if parsed.path.startswith("/oa/transcript/session/"):
                    session_id = parsed.path.removeprefix("/oa/transcript/session/")
                    try:
                        payload = build_session_transcript(
                            store=session_store,
                            session_id=session_id,
                            source="worker",
                        )
                    except ValueError:
                        _write_json(self, 400, {"error": "invalid_session_id"})
                        return
                    except FileNotFoundError:
                        _write_json(self, 404, {"error": "transcript_not_found"})
                        return
                    except Exception as exc:  # noqa: BLE001
                        _write_json(self, 500, {"error": "transcript_unavailable", "detail": str(exc)})
                        return
                    _write_json(self, 200, payload)
                    return
                if parsed.path != "/stream":
                    _write_json(self, 404, {"error": "not_found"})
                    return

                query = urllib_parse.parse_qs(parsed.query)
                execution_id = query.get("execution_id", [""])[0]
                mailbox = query.get("mailbox", ["child_events"])[0] or "child_events"
                after_seq_raw = query.get("after_seq", ["0"])[0]
                try:
                    after_seq = int(after_seq_raw or "0")
                except ValueError:
                    _write_json(self, 400, {"error": "invalid_after_seq"})
                    return
                state = _lookup_state(execution_id)
                if state is None:
                    _write_json(self, 404, {"error": "unknown_execution"})
                    return

                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("X-OA-Child-Session-ID", state.child_session_id)
                self.send_header("X-OA-Target-Node", state.target_node)
                self.send_header("X-OA-Git-Revision", state.git_revision)
                self.send_header("X-OA-Worker-Execution-ID", state.worker_execution_id or "")
                self.send_header("X-OA-Execution-ID", state.execution_id)
                self.end_headers()
                _stream_execution(self, state=state, mailbox=mailbox, after_seq=after_seq)

            def do_POST(self):  # noqa: N802
                if self.path == "/send":
                    body = _read_json(self)
                    if body is None:
                        return
                    envelope = ActorEnvelope.from_dict(body)
                    state = _lookup_state(envelope.execution_id)
                    if state is None:
                        _write_json(self, 404, {"error": "unknown_execution"})
                        return
                    if envelope.kind == "ack":
                        acked_seq = envelope.seq
                        if isinstance(envelope.payload, Mapping):
                            payload_seq = envelope.payload.get("acked_seq")
                            if isinstance(payload_seq, int) and payload_seq > 0:
                                acked_seq = payload_seq
                        state.record_ack(mailbox=envelope.mailbox, acked_seq=acked_seq)
                        _write_json(self, 202, {"ok": True, "execution_id": envelope.execution_id, "acked_seq": acked_seq})
                        return
                    asyncio.run(state.handle.send(envelope))
                    _write_json(self, 202, {"ok": True, "execution_id": envelope.execution_id})
                    return

                if self.path == "/abort":
                    body = _read_json(self)
                    if body is None:
                        return
                    execution_id = str(body.get("execution_id") or "")
                    state = _lookup_state(execution_id)
                    if state is None:
                        _write_json(self, 404, {"error": "unknown_execution"})
                        return
                    asyncio.run(state.handle.abort())
                    _write_json(self, 202, {"ok": True, "execution_id": execution_id})
                    return

                if self.path == "/close":
                    body = _read_json(self)
                    if body is None:
                        return
                    execution_id = str(body.get("execution_id") or "")
                    state = _lookup_state(execution_id)
                    if state is None:
                        _write_json(self, 202, {"ok": True, "execution_id": execution_id, "already_closed": True})
                        return
                    first_request = state.request_close()
                    if state.done and state.begin_close_finalization():
                        _finalize_close(state)
                    _write_json(
                        self,
                        202,
                        {
                            "ok": True,
                            "execution_id": execution_id,
                            "close_requested": True,
                            "first_request": first_request,
                        },
                    )
                    return

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
                    slots = _execution_slots_for(effective_request.definition.worker.max_concurrent_tasks)
                    slots.acquire()
                    try:
                        state = _start_execution(effective_request, slots=slots)
                    except Exception:
                        slots.release()
                        raise

                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("X-OA-Child-Session-ID", state.child_session_id)
                    self.send_header("X-OA-Target-Node", state.target_node)
                    self.send_header("X-OA-Git-Revision", state.git_revision)
                    self.send_header("X-OA-Worker-Execution-ID", state.worker_execution_id or "")
                    self.send_header("X-OA-Execution-ID", state.execution_id)
                    self.end_headers()
                    _stream_execution(self, state=state, mailbox="child_events", after_seq=0)
                except Exception as exc:  # noqa: BLE001
                    _write_json(self, 500, {"error": str(exc)})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        return ThreadingHTTPServer((self._host, self._port), Handler)


def _stream_execution(
    handler: BaseHTTPRequestHandler,
    *,
    state: _ServerExecutionState,
    mailbox: str,
    after_seq: int,
) -> None:
    next_seq = after_seq
    while True:
        with state.condition:
            pending = [envelope for envelope in state.envelopes if envelope.mailbox == mailbox and envelope.seq > next_seq]
            done = state.done
            if not pending and not done:
                state.condition.wait(timeout=0.1)
                continue
        for envelope in pending:
            raw = json.dumps(envelope.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n"
            try:
                handler.wfile.write(raw)
                handler.wfile.flush()
            except OSError:
                return
            next_seq = envelope.seq
        if done and not pending:
            return


async def _read_envelopes_from_response(response) -> AsyncIterator[ActorEnvelope]:
    while True:
        line = await asyncio.to_thread(response.readline)
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip() if isinstance(line, bytes) else str(line).strip()
        if not text:
            continue
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise RuntimeError("remote actor stream yielded a non-object JSON line")
        yield ActorEnvelope.from_dict(obj)


def _down_envelope_from_down(*, down: ActorDownEvent, seq: int) -> ActorEnvelope:
    return ActorEnvelope(
        protocol_version="v1",
        message_id=uuid.uuid4().hex,
        execution_id=down.execution_id,
        sender_actor_id=down.actor_id,
        recipient_actor_id="host",
        mailbox="child_events",
        seq=seq,
        kind="down",
        payload=down.to_payload(),
        ts=0.0,
    )


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
        "worker_execution_id": request.worker_execution_id,
        "trace_context": dict(request.trace_context),
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
        worker_execution_id=(str(obj.get("worker_execution_id")) if isinstance(obj.get("worker_execution_id"), str) else None),
        trace_context=_trace_context_from_dict(obj.get("trace_context")),
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


def _trace_context_from_dict(raw: Any) -> dict[str, str]:
    obj = raw if isinstance(raw, Mapping) else {}
    result: dict[str, str] = {}
    for key, value in obj.items():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result


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
