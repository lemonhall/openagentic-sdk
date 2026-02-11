from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from .base import ModelOutput, ToolCall
from .sse import parse_sse_events
from .stream_events import DoneEvent, TextDeltaEvent, ToolCallEvent

Transport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]]
StreamTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Iterable[bytes]]

_RETRYABLE_HTTP_STATUS: set[int] = {408, 409, 425, 429, 500, 502, 503, 504}


def _backoff_seconds(attempt_index: int, base: float) -> float:
    # attempt_index: 0 for first retry, 1 for second retry, ...
    if attempt_index < 0:
        return 0.0
    return max(0.0, base) * (2**attempt_index)


def _read_http_error_body(e: urllib.error.HTTPError) -> str:
    try:
        return e.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _runtime_http_error(url: str, e: urllib.error.HTTPError) -> RuntimeError:
    body = _read_http_error_body(e)
    hint = " (transient upstream error; try again)" if int(getattr(e, "code", 0)) in _RETRYABLE_HTTP_STATUS else ""
    return RuntimeError(f"HTTP {e.code} from {url}{hint}: {body}".strip())


def _default_transport(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    timeout_s: float,
    max_retries: int = 0,
    retry_backoff_s: float = 0.5,
) -> Mapping[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    last_exc: Exception | None = None
    max_retries = max(0, int(max_retries))
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            last_exc = e
            if attempt < max_retries and int(getattr(e, "code", 0)) in _RETRYABLE_HTTP_STATUS:
                time.sleep(_backoff_seconds(attempt, retry_backoff_s))
                continue
            raise _runtime_http_error(url, e) from e
        except urllib.error.URLError as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(_backoff_seconds(attempt, retry_backoff_s))
                continue
            raise RuntimeError(f"Request failed to {url}: {e}".strip()) from e
    else:  # pragma: no cover
        raise RuntimeError(f"Request failed to {url}: {last_exc}".strip()) from last_exc

    if not raw:
        raise RuntimeError(f"Empty response body from {url}")

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        # Some OpenAI-compatible gateways may respond with SSE even when the
        # request did not explicitly set stream=true. Best-effort: parse the
        # SSE transcript and synthesize a Responses-like object.
        if b"data:" in raw[:2000]:
            out_text: list[str] = []
            response_id: str | None = None
            usage: Mapping[str, Any] | None = None
            ongoing: dict[int, dict[str, Any]] = {}
            tool_calls: list[Mapping[str, Any]] = []

            for data in parse_sse_events(_iter_lines(raw.splitlines(keepends=True))):
                if data.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                typ = obj.get("type")
                if not isinstance(typ, str):
                    continue

                rid0 = obj.get("response_id")
                if isinstance(rid0, str) and rid0:
                    response_id = rid0

                if typ == "response.created":
                    resp_obj = obj.get("response")
                    if isinstance(resp_obj, dict):
                        rid = resp_obj.get("id")
                        if isinstance(rid, str) and rid:
                            response_id = rid
                    continue

                if typ == "response.output_text.delta":
                    delta = obj.get("delta")
                    if isinstance(delta, str) and delta:
                        out_text.append(delta)
                    continue

                if typ == "response.output_item.added":
                    output_index = obj.get("output_index")
                    item = obj.get("item")
                    if isinstance(output_index, int) and isinstance(item, dict) and item.get("type") == "function_call":
                        call_id = item.get("call_id")
                        name = item.get("name")
                        if isinstance(call_id, str) and call_id and isinstance(name, str) and name:
                            ongoing[output_index] = {"call_id": call_id, "name": name, "arguments": ""}
                    continue

                if typ == "response.function_call_arguments.delta":
                    output_index = obj.get("output_index")
                    delta = obj.get("delta")
                    if isinstance(output_index, int) and isinstance(delta, str) and output_index in ongoing:
                        ongoing[output_index]["arguments"] += delta
                    continue

                if typ == "response.output_item.done":
                    output_index = obj.get("output_index")
                    item = obj.get("item")
                    if isinstance(output_index, int) and isinstance(item, dict) and item.get("type") == "function_call":
                        st = ongoing.get(output_index) or {}
                        call_id = st.get("call_id") or item.get("call_id")
                        name = st.get("name") or item.get("name")
                        arguments = st.get("arguments") or item.get("arguments") or ""
                        if isinstance(call_id, str) and call_id and isinstance(name, str) and name:
                            tool_calls.append({"type": "function_call", "call_id": call_id, "name": name, "arguments": arguments})
                    continue

                if typ == "response.completed":
                    resp_obj = obj.get("response")
                    if isinstance(resp_obj, dict):
                        rid = resp_obj.get("id")
                        if isinstance(rid, str) and rid:
                            response_id = rid
                        u = resp_obj.get("usage")
                        usage = u if isinstance(u, dict) else usage
                    continue

            output_items: list[Mapping[str, Any]] = []
            text = "".join(out_text).strip()
            if text:
                output_items.append({"type": "message", "content": [{"type": "output_text", "text": text}]})
            output_items.extend(tool_calls)
            return {"id": response_id, "output": output_items, "usage": usage}

        snippet = raw[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"Non-JSON response from {url}: {snippet!r}") from e


def _default_stream_transport(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    timeout_s: float,
    max_retries: int = 0,
    retry_backoff_s: float = 0.5,
) -> Iterable[bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    max_retries = max(0, int(max_retries))
    resp = None
    for attempt in range(max_retries + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout_s)
            break
        except urllib.error.HTTPError as e:
            if attempt < max_retries and int(getattr(e, "code", 0)) in _RETRYABLE_HTTP_STATUS:
                time.sleep(_backoff_seconds(attempt, retry_backoff_s))
                continue
            raise _runtime_http_error(url, e) from e
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(_backoff_seconds(attempt, retry_backoff_s))
                continue
            raise RuntimeError(f"Request failed to {url}: {e}".strip()) from e
    if resp is None:  # pragma: no cover
        raise RuntimeError(f"Request failed to {url}".strip())
    try:
        while True:
            chunk = resp.readline()
            if not chunk:
                break
            yield chunk
    finally:
        resp.close()


def _iter_lines(chunks: Iterable[bytes]) -> Iterable[bytes]:
    buf = b""
    for chunk in chunks:
        if not chunk:
            continue
        buf += chunk
        while True:
            idx = buf.find(b"\n")
            if idx < 0:
                break
            line = buf[: idx + 1]
            buf = buf[idx + 1 :]
            yield line
    if buf:
        yield buf


def _parse_tool_call(item: Mapping[str, Any]) -> ToolCall | None:
    call_id = item.get("call_id")
    name = item.get("name")
    args_raw = item.get("arguments")
    if not isinstance(call_id, str) or not call_id:
        return None
    if not isinstance(name, str) or not name:
        return None
    args: dict[str, Any]
    if isinstance(args_raw, str):
        try:
            args = json.loads(args_raw) if args_raw.strip() else {}
        except json.JSONDecodeError:
            args = {"_raw": args_raw}
    elif isinstance(args_raw, dict):
        args = dict(args_raw)
    else:
        args = {"_raw": args_raw}
    return ToolCall(tool_use_id=call_id, name=name, arguments=args)


def _parse_assistant_text(output_items: Sequence[Mapping[str, Any]]) -> str | None:
    parts: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
    if not parts:
        return None
    return "".join(parts)


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProvider:
    name: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key_header: str = "authorization"
    timeout_s: float = 60.0
    max_retries: int = 0
    retry_backoff_s: float = 0.5
    transport: Transport | None = None
    stream_transport: StreamTransport | None = None

    async def complete(
        self,
        *,
        model: str,
        input: Sequence[Mapping[str, Any]],
        instructions: str | None = None,
        tools: Sequence[Mapping[str, Any]] = (),
        api_key: str | None = None,
        previous_response_id: str | None = None,
        store: bool = True,
        include: Sequence[str] = (),
    ) -> ModelOutput:
        if not api_key:
            raise ValueError("OpenAICompatibleProvider: api_key is required")

        url = f"{self.base_url}/responses"
        headers = {"content-type": "application/json"}
        if self.api_key_header.lower() == "authorization":
            headers["authorization"] = f"Bearer {api_key}"
        else:
            headers[self.api_key_header] = api_key

        payload: dict[str, Any] = {"model": model, "input": list(input), "store": bool(store)}
        if isinstance(instructions, str) and instructions.strip():
            payload["instructions"] = instructions
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if include:
            payload["include"] = list(include)
        if tools:
            payload["tools"] = list(tools)

        if self.transport is None:
            obj = _default_transport(
                url,
                headers,
                payload,
                timeout_s=self.timeout_s,
                max_retries=self.max_retries,
                retry_backoff_s=self.retry_backoff_s,
            )
        else:
            obj = self.transport(url, headers, payload)
        output = obj.get("output")
        output_items: list[Mapping[str, Any]] = [x for x in (output or []) if isinstance(x, dict)]

        assistant_text = _parse_assistant_text(output_items)
        tool_calls_out: list[ToolCall] = []
        for item in output_items:
            if item.get("type") == "function_call":
                tc = _parse_tool_call(item)
                if tc is not None:
                    tool_calls_out.append(tc)

        return ModelOutput(
            assistant_text=assistant_text,
            tool_calls=tool_calls_out,
            usage=obj.get("usage") if isinstance(obj.get("usage"), dict) else None,
            raw=obj if isinstance(obj, dict) else None,
            response_id=obj.get("id") if isinstance(obj.get("id"), str) else None,
        )

    async def stream(
        self,
        *,
        model: str,
        input: Sequence[Mapping[str, Any]],
        instructions: str | None = None,
        tools: Sequence[Mapping[str, Any]] = (),
        api_key: str | None = None,
        previous_response_id: str | None = None,
        store: bool = True,
        include: Sequence[str] = (),
    ):
        if not api_key:
            raise ValueError("OpenAICompatibleProvider: api_key is required")

        url = f"{self.base_url}/responses"
        headers = {"content-type": "application/json"}
        if self.api_key_header.lower() == "authorization":
            headers["authorization"] = f"Bearer {api_key}"
        else:
            headers[self.api_key_header] = api_key

        payload: dict[str, Any] = {
            "model": model,
            "input": list(input),
            "stream": True,
            "store": bool(store),
        }
        if isinstance(instructions, str) and instructions.strip():
            payload["instructions"] = instructions
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if include:
            payload["include"] = list(include)
        if tools:
            payload["tools"] = list(tools)

        if self.stream_transport is None:
            chunks = _default_stream_transport(
                url,
                headers,
                payload,
                timeout_s=self.timeout_s,
                max_retries=self.max_retries,
                retry_backoff_s=self.retry_backoff_s,
            )
        else:
            chunks = self.stream_transport(url, headers, payload)

        ongoing: dict[int, dict[str, Any]] = {}
        for data in parse_sse_events(_iter_lines(chunks)):
            if data.strip() == "[DONE]":
                yield DoneEvent()
                return
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            typ = obj.get("type")
            if not isinstance(typ, str):
                continue

            if typ == "response.output_text.delta":
                delta = obj.get("delta")
                if isinstance(delta, str) and delta:
                    yield TextDeltaEvent(delta=delta)
                continue

            if typ == "response.output_item.added":
                output_index = obj.get("output_index")
                item = obj.get("item")
                if isinstance(output_index, int) and isinstance(item, dict) and item.get("type") == "function_call":
                    call_id = item.get("call_id")
                    name = item.get("name")
                    if isinstance(call_id, str) and call_id and isinstance(name, str) and name:
                        ongoing[output_index] = {"call_id": call_id, "name": name, "arguments": ""}
                continue

            if typ == "response.function_call_arguments.delta":
                output_index = obj.get("output_index")
                delta = obj.get("delta")
                if isinstance(output_index, int) and isinstance(delta, str) and output_index in ongoing:
                    ongoing[output_index]["arguments"] += delta
                continue

            if typ == "response.output_item.done":
                output_index = obj.get("output_index")
                item = obj.get("item")
                if isinstance(output_index, int) and isinstance(item, dict) and item.get("type") == "function_call":
                    st = ongoing.get(output_index) or {}
                    tc = _parse_tool_call(
                        {
                            "call_id": st.get("call_id") or item.get("call_id"),
                            "name": st.get("name") or item.get("name"),
                            "arguments": st.get("arguments") or item.get("arguments") or "",
                        }
                    )
                    if tc is not None:
                        yield ToolCallEvent(tool_call=tc)
                    ongoing.pop(output_index, None)
                continue

            if typ in ("response.completed", "response.incomplete"):
                yield DoneEvent()
                return

        yield DoneEvent()
