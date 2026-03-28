from __future__ import annotations

import asyncio
import json
import queue
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, AsyncIterator

from ..serialization import event_from_dict

_STREAM_END = object()


def _request_json(url: str, *, method: str, payload: dict[str, Any] | None = None, timeout_s: float = 10.0) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {"Connection": "close"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
            raw = resp.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"remote chat host is unreachable: {e.reason}") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"remote chat host returned HTTP {e.code}: {body}") from e
    obj = json.loads(raw.decode("utf-8", errors="replace"))
    return obj if isinstance(obj, dict) else {}


def _request_empty(url: str, *, method: str, payload: dict[str, Any] | None = None, timeout_s: float = 10.0) -> None:
    data = None
    headers: dict[str, str] = {"Connection": "close"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_s)):
            return
    except urllib.error.URLError as e:
        raise RuntimeError(f"remote chat host is unreachable: {e.reason}") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"remote chat host returned HTTP {e.code}: {body}") from e


class _SseStream:
    def __init__(self, *, url: str, timeout_s: float) -> None:
        self._url = url
        self._timeout_s = timeout_s
        self._queue: queue.Queue[object] = queue.Queue()
        self._response = None
        self._thread = threading.Thread(target=self._run, name="oa-cluster-chat-sse", daemon=True)
        self._thread.start()

    def close(self) -> None:
        response = self._response
        if response is not None:
            try:
                fp = getattr(response, "fp", None)
                raw = getattr(fp, "raw", None)
                sock = getattr(raw, "_sock", None) or getattr(raw, "sock", None)
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                response.close()
            except Exception:
                pass
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            response = urllib.request.urlopen(
                urllib.request.Request(self._url, headers={"Connection": "close"}),
                timeout=float(self._timeout_s),
            )
            self._response = response
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                obj = json.loads(payload)
                if isinstance(obj, dict):
                    self._queue.put(obj)
        except Exception as e:  # noqa: BLE001
            self._queue.put(e)
        finally:
            self._queue.put(_STREAM_END)

    async def next(self) -> dict[str, Any]:
        item = await asyncio.to_thread(self._queue.get)
        if item is _STREAM_END:
            raise RuntimeError("remote chat event stream ended unexpectedly")
        if isinstance(item, Exception):
            raise RuntimeError(str(item)) from item
        if not isinstance(item, dict):
            raise RuntimeError("remote chat event stream produced a non-object payload")
        return item


@dataclass(frozen=True, slots=True)
class ClusterChatClient:
    base_url: str
    timeout_s: float = 10.0

    def health(self) -> dict[str, Any]:
        return _request_json(self.base_url.rstrip("/") + "/health", method="GET", timeout_s=self.timeout_s)

    def get_session(self, *, session_id: str) -> dict[str, Any]:
        return _request_json(self.base_url.rstrip("/") + f"/session/{session_id}", method="GET", timeout_s=self.timeout_s)

    def create_session(self, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return _request_json(
            self.base_url.rstrip("/") + "/session",
            method="POST",
            payload={"metadata": metadata or {}},
            timeout_s=self.timeout_s,
        )

    def prompt_async(self, *, session_id: str, prompt: str) -> None:
        _request_empty(
            self.base_url.rstrip("/") + f"/session/{session_id}/prompt_async",
            method="POST",
            payload={"prompt": prompt},
            timeout_s=self.timeout_s,
        )

    def abort(self, *, session_id: str) -> None:
        _request_empty(
            self.base_url.rstrip("/") + f"/session/{session_id}/abort",
            method="POST",
            timeout_s=self.timeout_s,
        )

    async def query(
        self,
        *,
        prompt: str,
        session_id: str | None = None,
        abort_event: Any | None = None,
    ) -> AsyncIterator[Any]:
        if not session_id:
            health = self.health()
            metadata: dict[str, Any] = {}
            git_revision = health.get("git_revision")
            if isinstance(git_revision, str) and git_revision:
                metadata["git_revision"] = git_revision
                metadata["authoritative_revision"] = git_revision
            host_node_name = health.get("host_node_name")
            if isinstance(host_node_name, str) and host_node_name:
                metadata["host_node_name"] = host_node_name
            created = self.create_session(metadata=metadata)
            sid = created.get("id")
            if not isinstance(sid, str) or not sid:
                raise RuntimeError("remote chat host did not return a session id")
            session_id = sid

        stream = _SseStream(url=self.base_url.rstrip("/") + "/event", timeout_s=self.timeout_s)
        abort_task: asyncio.Task[None] | None = None
        try:
            while True:
                ready_payload = await stream.next()
                if ready_payload.get("type") == "server.connected":
                    break
            if abort_event is not None and hasattr(abort_event, "wait"):
                async def _relay_abort() -> None:
                    await abort_event.wait()
                    self.abort(session_id=session_id)

                abort_task = asyncio.create_task(_relay_abort())

            self.prompt_async(session_id=session_id, prompt=prompt)
            seen_result = False
            while True:
                payload = await stream.next()
                envelope_type = payload.get("type")
                envelope_session_id = payload.get("session_id")
                if envelope_type == "session.event" and envelope_session_id == session_id:
                    event_payload = payload.get("event")
                    if not isinstance(event_payload, dict):
                        raise RuntimeError("remote chat host returned an invalid event payload")
                    event = event_from_dict(event_payload)
                    yield event
                    if getattr(event, "type", None) == "result":
                        seen_result = True
                    continue
                if envelope_type == "session.sync" and envelope_session_id == session_id:
                    sync_payload = payload.get("sync")
                    sync_obj = sync_payload if isinstance(sync_payload, dict) else {}
                    status = sync_obj.get("status")
                    reason = sync_obj.get("reason")
                    if status != "ok":
                        suffix = f": {reason}" if isinstance(reason, str) and reason else ""
                        raise RuntimeError(f"remote session sync failed ({status}){suffix}")
                    if seen_result:
                        return
                    raise RuntimeError("remote session ended before emitting a result event")
        finally:
            stream.close()
            if abort_task is not None:
                abort_task.cancel()


class ClusterChatRuntime:
    def __init__(self, options) -> None:  # noqa: ANN001
        self._options = options
        base_url = getattr(options, "remote_chat_base_url", None)
        timeout_s = float(getattr(options, "remote_chat_timeout_s", 10.0) or 10.0)
        if not isinstance(base_url, str) or not base_url:
            raise RuntimeError("remote chat runtime requires options.remote_chat_base_url")
        self._client = ClusterChatClient(base_url=base_url, timeout_s=timeout_s)

    async def query(self, prompt: str) -> AsyncIterator[Any]:
        async for event in self._client.query(
            prompt=prompt,
            session_id=self._options.resume,
            abort_event=self._options.abort_event,
        ):
            yield event
