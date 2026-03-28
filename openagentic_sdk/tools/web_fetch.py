from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .base import Tool, ToolContext

FetchTransport = Callable[[str, Mapping[str, str]], tuple[int, Mapping[str, str], bytes]]
ExtractTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]]

_getaddrinfo = socket.getaddrinfo
_HTML_BLOCK_MARKERS = (
    "error code: 1010",
    "access denied",
    "captcha",
    "cf-chl",
    "challenge-platform",
    "enable javascript",
    "just a moment",
    "forbidden",
    "waf",
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Prevent urllib from transparently following redirects. We need to enforce
    # host allow/deny checks on every hop.
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _ = (req, fp, code, msg, headers, newurl)
        return None


def _default_fetch_transport(url: str, headers: Mapping[str, str]) -> tuple[int, Mapping[str, str], bytes]:
    req = urllib.request.Request(url, method="GET")
    for k, v in headers.items():
        req.add_header(k, v)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=60) as resp:
            status = int(getattr(resp, "status", 200))
            resp_headers = {k.lower(): v for k, v in dict(resp.headers).items()}
            body = resp.read()
    except urllib.error.HTTPError as e:
        # urllib raises for 3xx when redirects are disabled; treat as a response.
        status = int(getattr(e, "code", 0) or 0)
        resp_headers = {k.lower(): v for k, v in dict(getattr(e, "headers", {}) or {}).items()}
        try:
            body = e.read()  # type: ignore[assignment]
        except Exception:  # noqa: BLE001
            body = b""
    return status, resp_headers, body


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


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _visible_text_from_html(text: str) -> str:
    without_scripts = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(r"<style\b.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_styles)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _html_shell_reason(*, content_type: str | None, text: str) -> str | None:
    if not isinstance(content_type, str) or "html" not in content_type.lower():
        return None
    lowered = text.lower()
    if any(marker in lowered for marker in _HTML_BLOCK_MARKERS):
        return "html_blocked"
    visible_text = _visible_text_from_html(text)
    script_count = len(re.findall(r"<script\b", lowered))
    if script_count >= 3 and len(visible_text) < 200:
        return "html_shell"
    if script_count >= 8 and visible_text.count(" - ") >= 20:
        return "html_shell"
    if len(visible_text) < 120 and any(
        marker in lowered for marker in ("id='app'", 'id="app"', "id='root'", 'id="root"', "__next", "window.__")
    ):
        return "html_shell"
    return None


@dataclass(frozen=True, slots=True)
class WebFetchTool(Tool):
    name: str = "WebFetch"
    description: str = "Fetch a URL over HTTP(S), with optional Tavily Extract fallback for blocked or JS-shell pages."
    max_bytes: int = 1024 * 1024
    max_redirects: int = 5
    allow_private_networks: bool = False
    transport: FetchTransport = _default_fetch_transport
    extract_transport: ExtractTransport = _default_extract_transport
    extract_endpoint: str = "https://api.tavily.com/extract"

    def _validate_url(self, url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("WebFetch: only http/https URLs are allowed")
        if not parsed.hostname:
            raise ValueError("WebFetch: URL must include a hostname")
        if not self.allow_private_networks and _is_blocked_host(parsed.hostname):
            raise ValueError("WebFetch: blocked hostname")
        return parsed

    def _coerce_headers(self, headers: Mapping[str, Any]) -> dict[str, str]:
        return {str(k).lower(): str(v) for k, v in headers.items()}

    def _next_url_from_location(self, *, current_url: str, location: str) -> str:
        # Location can be relative; join against the current URL.
        return urllib.parse.urljoin(current_url, location)

    def _tavily_extract_enabled(self) -> bool:
        if not _env_flag("OPENAGENTIC_WEBFETCH_TAVILY_EXTRACT", default=True):
            return False
        api_key = os.environ.get("TAVILY_API_KEY")
        return isinstance(api_key, str) and bool(api_key.strip())

    def _tavily_extract_depth(self) -> str:
        depth = (os.environ.get("OPENAGENTIC_WEBFETCH_TAVILY_EXTRACT_DEPTH") or "advanced").strip().lower()
        return depth if depth in ("basic", "advanced") else "advanced"

    def _tavily_extract_format(self) -> str:
        fmt = (os.environ.get("OPENAGENTIC_WEBFETCH_TAVILY_FORMAT") or "markdown").strip().lower()
        return fmt if fmt in ("markdown", "text") else "markdown"

    def _should_try_tavily_extract(
        self,
        *,
        final_url: str,
        status: int,
        content_type: str | None,
        text: str,
        headers: Mapping[str, str],
    ) -> str | None:
        if not self._tavily_extract_enabled():
            return None
        if headers:
            return None
        parsed = urllib.parse.urlparse(final_url)
        host = parsed.hostname or ""
        if not host or _is_blocked_host(host):
            return None
        if status >= 400:
            return f"http_status:{status}"
        return _html_shell_reason(content_type=content_type, text=text)

    def _extract_with_tavily(self, *, url: str) -> dict[str, Any]:
        api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("missing TAVILY_API_KEY")

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
        failed_results = obj.get("failed_results") if isinstance(obj, dict) else None
        response_time = obj.get("response_time") if isinstance(obj, dict) else None
        request_id = obj.get("request_id") if isinstance(obj, dict) else None

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

        raw_content = str(result.get("raw_content") or "")
        return {
            "url": str(result.get("url") or url),
            "text": raw_content,
            "request_id": request_id if isinstance(request_id, str) else None,
            "response_time": response_time if isinstance(response_time, (int, float)) else None,
            "extract_depth": payload["extract_depth"],
            "format": payload["format"],
        }

    def _fetch_following_redirects(
        self, *, url: str, headers: Mapping[str, str]
    ) -> tuple[str, int, Mapping[str, str], bytes, list[str]]:
        chain: list[str] = [url]
        current_url = url
        for _ in range(max(0, int(self.max_redirects)) + 1):
            status, resp_headers_raw, body = self.transport(current_url, headers)
            resp_headers = {str(k).lower(): str(v) for k, v in (resp_headers_raw or {}).items()}

            if status in (301, 302, 303, 307, 308):
                loc = resp_headers.get("location")
                if not loc:
                    return current_url, status, resp_headers, body, chain
                next_url = self._next_url_from_location(current_url=current_url, location=loc)
                self._validate_url(next_url)
                current_url = next_url
                chain.append(current_url)
                continue

            return current_url, status, resp_headers, body, chain

        raise ValueError(f"WebFetch: too many redirects (>{self.max_redirects})")

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        url = tool_input.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("WebFetch: 'url' must be a non-empty string")
        requested_url = url
        self._validate_url(requested_url)

        headers = tool_input.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError("WebFetch: 'headers' must be an object")

        final_url, status, resp_headers, body, redirect_chain = self._fetch_following_redirects(
            url=requested_url, headers=self._coerce_headers(headers)
        )
        if len(body) > self.max_bytes:
            body = body[: self.max_bytes]

        content_type = resp_headers.get("content-type")
        text = body.decode("utf-8", errors="replace")
        output: dict[str, Any] = {
            # Keep compatibility while making the final URL explicit.
            "requested_url": requested_url,
            "url": final_url,
            "final_url": final_url,
            "redirect_chain": list(redirect_chain),
            "status": status,
            "content_type": content_type,
            "text": text,
            "backend": "direct",
        }

        fallback_reason = self._should_try_tavily_extract(
            final_url=final_url,
            status=status,
            content_type=content_type,
            text=text,
            headers=self._coerce_headers(headers),
        )
        if not isinstance(fallback_reason, str) or not fallback_reason:
            return output

        try:
            extracted = self._extract_with_tavily(url=final_url)
        except Exception as exc:  # noqa: BLE001
            output["tavily_extract_attempted"] = True
            output["tavily_extract_error"] = str(exc)
            return output

        extracted_format = str(extracted.get("format") or "markdown")
        output.update(
            {
                "url": extracted.get("url") or final_url,
                "final_url": extracted.get("url") or final_url,
                "status": 200,
                "content_type": "text/plain" if extracted_format == "text" else "text/markdown",
                "text": extracted.get("text") or "",
                "backend": "tavily_extract",
                "fallback_reason": fallback_reason,
                "direct_status": status,
                "direct_content_type": content_type,
                "request_id": extracted.get("request_id"),
                "response_time": extracted.get("response_time"),
                "extract_depth": extracted.get("extract_depth"),
                "format": extracted_format,
            }
        )
        return output
