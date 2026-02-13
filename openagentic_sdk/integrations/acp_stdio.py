from __future__ import annotations

import asyncio
import json
import sys
import threading
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from ..api import query as query_events
from ..events import AssistantDelta, AssistantMessage, Result, ToolResult, ToolUse, UserMessage
from ..options import OpenAgenticOptions
from ..paths import default_session_root
from ..permissions.gate import PermissionGate
from ..sessions.store import FileSessionStore


JsonObj = dict[str, Any]


def _json_dumps_one_line(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    # ACP stdio transport: one JSON-RPC message per line.
    if "\n" in s or "\r" in s:
        s = s.replace("\r", "\\r").replace("\n", "\\n")
    return s


@dataclass(slots=True)
class _SessionState:
    cwd: str
    abort_event: threading.Event


class _Deferred:
    pass


class AcpStdioServer:
    def __init__(self, options: OpenAgenticOptions) -> None:
        self._base_options = options
        store = options.session_store
        if store is None:
            root = options.session_root or default_session_root()
            store = FileSessionStore(root_dir=Path(root))
        self._store = store

        self._write_lock = asyncio.Lock()
        self._initialized = False
        self._protocol_version = "1"

        self._next_id = 1
        self._pending: dict[int, asyncio.Future[JsonObj]] = {}
        self._pending_session: dict[int, str] = {}

        self._sessions: dict[str, _SessionState] = {}

    async def _write(self, obj: Any) -> None:
        line = _json_dumps_one_line(obj)
        async with self._write_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    async def _respond_result(self, rid: Any, result: Any) -> None:
        await self._write({"jsonrpc": "2.0", "id": rid, "result": result})

    async def _respond_error(self, rid: Any, *, code: int, message: str) -> None:
        await self._write({"jsonrpc": "2.0", "id": rid, "error": {"code": int(code), "message": str(message)}})

    async def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _alloc_id(self) -> int:
        rid = self._next_id
        self._next_id += 1
        return rid

    async def _request(self, *, method: str, params: Mapping[str, Any], session_id: str | None = None) -> JsonObj:
        rid = self._alloc_id()
        fut: asyncio.Future[JsonObj] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        if session_id is not None:
            self._pending_session[rid] = session_id
        await self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": dict(params)})
        try:
            return await asyncio.wait_for(fut, timeout=300.0)
        finally:
            self._pending.pop(rid, None)
            self._pending_session.pop(rid, None)

    async def serve_forever(self) -> None:
        while True:
            line_b = await asyncio.to_thread(sys.stdin.buffer.readline)
            if not line_b:
                return
            line = line_b.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                # Transport requires valid JSON only; ignore junk.
                continue
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                continue
            asyncio.create_task(self._handle_message(msg))

    async def _handle_message(self, msg: JsonObj) -> None:
        if "method" in msg:
            if "id" in msg:
                await self._handle_request(msg)
            else:
                await self._handle_notification(msg)
            return
        if "id" in msg:
            self._handle_response(msg)

    def _handle_response(self, msg: JsonObj) -> None:
        rid = msg.get("id")
        if not isinstance(rid, int):
            return
        fut = self._pending.get(rid)
        if fut is None or fut.done():
            return
        fut.set_result(msg)

    async def _handle_request(self, msg: JsonObj) -> None:
        rid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params")
        if not isinstance(method, str):
            await self._respond_error(rid, code=-32600, message="Invalid request")
            return
        if params is None:
            params_obj: dict[str, Any] = {}
        elif isinstance(params, dict):
            params_obj = params
        else:
            await self._respond_error(rid, code=-32602, message="Invalid params")
            return

        try:
            out = await self._dispatch_request(method=method, params=params_obj, request_id=rid)
        except NotImplementedError:
            await self._respond_error(rid, code=-32601, message="Method not found")
            return
        except Exception as e:  # noqa: BLE001
            await self._respond_error(rid, code=-32603, message=str(e) or "Internal error")
            return
        if out is _Deferred:
            return
        await self._respond_result(rid, out)

    async def _handle_notification(self, msg: JsonObj) -> None:
        method = msg.get("method")
        params = msg.get("params")
        if not isinstance(method, str):
            return
        params_obj: dict[str, Any] = params if isinstance(params, dict) else {}
        if method == "session/cancel":
            sid = params_obj.get("sessionId")
            if isinstance(sid, str) and sid:
                st = self._sessions.get(sid)
                if st is not None:
                    st.abort_event.set()
                # Best-effort: unblock any pending permission requests.
                for pid, sess in list(self._pending_session.items()):
                    if sess != sid:
                        continue
                    fut = self._pending.get(pid)
                    if fut is not None and not fut.done():
                        fut.set_result({"jsonrpc": "2.0", "id": pid, "result": {"outcome": {"outcome": "cancelled"}}})
            return

    async def _dispatch_request(self, *, method: str, params: dict[str, Any], request_id: Any) -> Any:
        if method == "initialize":
            pv = params.get("protocolVersion")
            if isinstance(pv, str) and pv:
                self._protocol_version = pv
            self._initialized = True
            return {
                "protocolVersion": self._protocol_version,
                "agentInfo": {"name": "openagentic-sdk", "version": "dev"},
                # Keep capabilities minimal until we implement more surfaces.
                "agentCapabilities": {"loadSession": True},
            }

        if not self._initialized:
            raise RuntimeError("ACP: initialize required")

        if method == "session/new":
            cwd = params.get("cwd")
            cwd2 = str(cwd) if isinstance(cwd, str) and cwd else self._base_options.cwd
            sid = self._store.create_session(metadata={"cwd": cwd2})
            self._sessions[sid] = _SessionState(cwd=cwd2, abort_event=threading.Event())
            return {"sessionId": sid}

        if method == "session/prompt":
            sid = params.get("sessionId")
            prompt = params.get("prompt")
            if not isinstance(sid, str) or not sid:
                raise RuntimeError("invalid sessionId")
            if not isinstance(prompt, str):
                raise RuntimeError("invalid prompt")
            if sid not in self._sessions:
                # Allow replay on an existing session id even if created elsewhere.
                self._sessions[sid] = _SessionState(cwd=self._base_options.cwd, abort_event=threading.Event())
            st = self._sessions[sid]
            st.abort_event = threading.Event()
            asyncio.create_task(self._run_prompt_turn(session_id=sid, prompt=prompt, request_id=request_id))
            return _Deferred

        if method == "session/load":
            sid = params.get("sessionId")
            cwd = params.get("cwd")
            if not isinstance(sid, str) or not sid:
                raise RuntimeError("invalid sessionId")
            cwd2 = str(cwd) if isinstance(cwd, str) and cwd else self._base_options.cwd
            if sid not in self._sessions:
                self._sessions[sid] = _SessionState(cwd=cwd2, abort_event=threading.Event())
            else:
                self._sessions[sid].cwd = cwd2

            # Replay persisted history as session/update notifications.
            for ev in self._store.read_events(sid):
                await self._emit_event_update(session_id=sid, ev=ev)
            return {}

        raise NotImplementedError(method)

    async def _run_prompt_turn(self, *, session_id: str, prompt: str, request_id: Any) -> None:
        st = self._sessions.get(session_id)
        if st is None:
            return

        # ACP requires interactive approvals to be negotiated via JSON-RPC.
        async def _approver(tool_name: str, tool_input: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
            # Treat UX-only tools as safe.
            if tool_name in {"Read", "Glob", "Grep", "Skill", "SlashCommand", "AskUserQuestion", "TodoWrite"}:
                return True

            tool_use_id = context.get("tool_use_id")
            tool_call_id = str(tool_use_id) if isinstance(tool_use_id, str) and tool_use_id else ""
            req = {
                "sessionId": session_id,
                "toolCall": {
                    "toolCallId": tool_call_id,
                    "title": tool_name,
                    "kind": "execute",
                    "input": dict(tool_input),
                },
                "options": [
                    {"optionId": "allow", "label": "Allow"},
                    {"optionId": "deny", "label": "Deny"},
                ],
            }
            resp = await self._request(method="session/request_permission", params=req, session_id=session_id)
            result = resp.get("result") if isinstance(resp, dict) else None
            outcome = result.get("outcome") if isinstance(result, dict) else None
            if isinstance(outcome, dict) and outcome.get("outcome") == "cancelled":
                st.abort_event.set()
                return False
            if isinstance(outcome, dict) and outcome.get("outcome") == "selected":
                return outcome.get("optionId") == "allow"
            return False

        gate = PermissionGate(permission_mode="callback", approver=_approver, interactive=False)
        opts2 = replace(
            self._base_options,
            resume=session_id,
            session_store=self._store,
            cwd=st.cwd,
            project_dir=st.cwd,
            abort_event=st.abort_event,
            include_partial_messages=True,
            permission_gate=gate,
        )

        stop_reason = "end"
        try:
            async for ev in query_events(prompt=prompt, options=opts2):
                await self._emit_event_update(session_id=session_id, ev=ev)
                if isinstance(ev, Result):
                    sr = getattr(ev, "stop_reason", None)
                    if isinstance(sr, str) and sr:
                        stop_reason = sr
        except Exception as e:  # noqa: BLE001
            await self._respond_error(request_id, code=-32603, message=str(e) or "Internal error")
            return

        # Map OpenAgentic stop reasons into ACP-like stopReason.
        if stop_reason == "interrupted":
            acp_stop = "cancelled"
        elif stop_reason == "max_steps":
            acp_stop = "max_steps"
        else:
            acp_stop = "end"
        await self._respond_result(request_id, {"stopReason": acp_stop})

    async def _emit_event_update(self, *, session_id: str, ev: Any) -> None:
        if isinstance(ev, AssistantDelta):
            text = getattr(ev, "text_delta", None)
            if isinstance(text, str) and text:
                await self._notify(
                    "session/update",
                    {"sessionId": session_id, "update": {"sessionUpdate": "agent_message_chunk", "content": text}},
                )
            return
        if isinstance(ev, AssistantMessage):
            text = getattr(ev, "text", None)
            if isinstance(text, str) and text:
                await self._notify(
                    "session/update",
                    {"sessionId": session_id, "update": {"sessionUpdate": "agent_message_chunk", "content": text}},
                )
            return
        if isinstance(ev, ToolUse):
            tid = getattr(ev, "tool_use_id", None)
            name = getattr(ev, "name", None)
            if isinstance(tid, str) and tid and isinstance(name, str) and name:
                await self._notify(
                    "session/update",
                    {
                        "sessionId": session_id,
                        "update": {"sessionUpdate": "tool_call", "toolCallId": tid, "title": name},
                    },
                )
            return
        if isinstance(ev, ToolResult):
            tid = getattr(ev, "tool_use_id", None)
            if isinstance(tid, str) and tid:
                status = "failed" if getattr(ev, "is_error", False) else "completed"
                upd: dict[str, Any] = {"sessionUpdate": "tool_call_update", "toolCallId": tid, "status": status}
                if getattr(ev, "is_error", False):
                    upd["error"] = {"message": str(getattr(ev, "error_message", "") or "")}
                else:
                    upd["output"] = getattr(ev, "output", None)
                await self._notify("session/update", {"sessionId": session_id, "update": upd})
            return
        if isinstance(ev, UserMessage):
            text = getattr(ev, "text", None)
            if isinstance(text, str) and text:
                await self._notify(
                    "session/update",
                    {"sessionId": session_id, "update": {"sessionUpdate": "user_message_chunk", "content": text}},
                )
            return


async def serve_acp_stdio(options: OpenAgenticOptions) -> None:
    """Run an ACP v1 JSON-RPC server over stdio (NDJSON framing)."""

    server = AcpStdioServer(options)
    await server.serve_forever()
