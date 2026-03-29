from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .base import Tool, ToolContext

LegacyFetchTransport = Callable[[str, Mapping[str, str]], tuple[int, Mapping[str, str], bytes]]
ExtractTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]]

_getaddrinfo = socket.getaddrinfo


def _default_extract_transport(url: str, headers: Mapping[str, str], payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _is_blocked_host(host: str) -> bool:
    host_lower = host.lower()
    if host_lower in ("localhost",):
        return True
    if host_lower.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = _getaddrinfo(host, 0)
        except Exception:  # noqa: BLE001
            return False
        for _family, _socktype, _proto, _canonname, sockaddr in infos:
            ip_str = None
            if isinstance(sockaddr, tuple) and sockaddr:
                ip_str = sockaddr[0]
            if not isinstance(ip_str, str) or not ip_str:
                continue
            try:
                ip2 = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if ip2.is_private or ip2.is_loopback or ip2.is_link_local:
                return True
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _truncate_utf8(text: str, *, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="ignore")


def _content_type_for_format(fmt: str) -> str:
    return "text/plain" if fmt == "text" else "text/markdown"


@dataclass(frozen=True, slots=True)
class WebFetchTool(Tool):
    name: str = "WebFetch"
    description: str = "Fetch a public web page via Tavily Extract."
    max_bytes: int = 1024 * 1024
    allow_private_networks: bool = False
    # Kept only for constructor compatibility while WebFetch is fully Tavily-backed.
    transport: LegacyFetchTransport | None = None
    extract_transport: ExtractTransport = _default_extract_transport
    extract_endpoint: str = "https://api.tavily.com/extract"

    def _validate_url(self, url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("WebFetch: only http/https URLs are allowed")
        if not parsed.hostname:
            raise ValueError("WebFetch: URL must include a hostname")
        if _is_blocked_host(parsed.hostname):
            raise ValueError("WebFetch: blocked hostname")
        return parsed

    def _coerce_headers(self, headers: Mapping[str, Any]) -> dict[str, str]:
        return {str(k).lower(): str(v) for k, v in headers.items()}

    def _tavily_extract_depth(self) -> str:
        depth = (os.environ.get("OPENAGENTIC_WEBFETCH_TAVILY_EXTRACT_DEPTH") or "advanced").strip().lower()
        return depth if depth in ("basic", "advanced") else "advanced"

    def _tavily_extract_format(self) -> str:
        fmt = (os.environ.get("OPENAGENTIC_WEBFETCH_TAVILY_FORMAT") or "markdown").strip().lower()
        return fmt if fmt in ("markdown", "text") else "markdown"

    def _extract_with_tavily(self, *, url: str) -> dict[str, Any]:
        api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("WebFetch requires TAVILY_API_KEY")

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        }
        payload: dict[str, Any] = {
            "api_key": api_key,
            "urls": [url],
            "extract_depth": self._tavily_extract_depth(),
            "format": self._tavily_extract_format(),
            "include_images": False,
            "include_favicon": False,
        }
        timeout_s = _env_float("OPENAGENTIC_WEBFETCH_TAVILY_TIMEOUT_S")
        if isinstance(timeout_s, float) and 1.0 <= timeout_s <= 60.0:
            payload["timeout"] = timeout_s

        obj = self.extract_transport(self.extract_endpoint, headers, payload)
        results_in = obj.get("results") if isinstance(obj, dict) else None
        response_time = obj.get("response_time") if isinstance(obj, dict) else None
        request_id = obj.get("request_id") if isinstance(obj, dict) else None
        failed_results = obj.get("failed_results") if isinstance(obj, dict) else None

        result: Mapping[str, Any] | None = None
        if isinstance(results_in, list):
            for item in results_in:
                if not isinstance(item, Mapping):
                    continue
                raw_content = item.get("raw_content")
                if isinstance(raw_content, str) and raw_content.strip():
                    result = item
                    break

        if result is None:
            msg = "tavily extract returned no raw_content"
            if isinstance(failed_results, list) and failed_results:
                first_failed = failed_results[0]
                if isinstance(first_failed, Mapping):
                    reason = first_failed.get("error") or first_failed.get("message")
                    if isinstance(reason, str) and reason.strip():
                        msg = reason.strip()
            raise RuntimeError(msg)

        raw_content = _truncate_utf8(str(result.get("raw_content") or ""), max_bytes=self.max_bytes)
        return {
            "url": str(result.get("url") or url),
            "text": raw_content,
            "request_id": request_id if isinstance(request_id, str) else None,
            "response_time": response_time if isinstance(response_time, (int, float)) else None,
            "extract_depth": payload["extract_depth"],
            "format": payload["format"],
        }

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        _ = ctx
        url = tool_input.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("WebFetch: 'url' must be a non-empty string")
        requested_url = url
        self._validate_url(requested_url)

        headers = tool_input.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError("WebFetch: 'headers' must be an object")
        if self._coerce_headers(headers):
            raise ValueError("WebFetch: custom headers are not supported by Tavily-backed WebFetch")

        extracted = self._extract_with_tavily(url=requested_url)
        final_url = str(extracted.get("url") or requested_url)
        redirect_chain = [requested_url] if final_url == requested_url else [requested_url, final_url]
        fmt = str(extracted.get("format") or "markdown")
        return {
            "requested_url": requested_url,
            "url": final_url,
            "final_url": final_url,
            "redirect_chain": redirect_chain,
            "status": 200,
            "content_type": _content_type_for_format(fmt),
            "text": str(extracted.get("text") or ""),
            "backend": "tavily_extract",
            "request_id": extracted.get("request_id"),
            "response_time": extracted.get("response_time"),
            "extract_depth": extracted.get("extract_depth"),
            "format": fmt,
        }
