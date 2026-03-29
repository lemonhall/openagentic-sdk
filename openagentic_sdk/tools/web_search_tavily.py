from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .base import Tool, ToolContext
from ._web_proxy import urlopen_with_proxy

SearchTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]]


def _default_search_transport(url: str, headers: Mapping[str, str], payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    with urlopen_with_proxy(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _domain_allowed(*, url: str, allowed_set: set[str], blocked_set: set[str]) -> bool:
    host = _host_of(url)
    if not host:
        return not allowed_set
    if blocked_set and any(host == b or host.endswith("." + b) for b in blocked_set):
        return False
    if allowed_set and not any(host == a or host.endswith("." + a) for a in allowed_set):
        return False
    return True


def _decode_duckduckgo_redirect(href: str) -> str:
    # DuckDuckGo HTML often wraps result URLs like:
    #   https://duckduckgo.com/l/?uddg=<percent-encoded-url>
    try:
        p = urllib.parse.urlparse(href)
    except Exception:  # noqa: BLE001
        return href
    qs = urllib.parse.parse_qs(p.query)
    uddg = qs.get("uddg")
    if uddg and isinstance(uddg, list) and uddg and isinstance(uddg[0], str):
        return urllib.parse.unquote(uddg[0])
    return href


def _duckduckgo_search(query: str, *, max_results: int, allowed_set: set[str], blocked_set: set[str]) -> list[dict[str, Any]]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "user-agent": "openagentic-sdk/0.1 (examples; +https://github.com/openai/openagentic-sdk)",
            "accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen_with_proxy(req, timeout=60) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError):
        return []

    text = raw.decode("utf-8", errors="replace")

    # Minimal HTML extraction for DDG results. We only need title+URL for examples.
    pat = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE)
    results: list[dict[str, Any]] = []
    for href, title_html in pat.findall(text):
        href2 = html.unescape(href)
        url2 = _decode_duckduckgo_redirect(href2)
        if not isinstance(url2, str) or not url2:
            continue
        if not _domain_allowed(url=url2, allowed_set=allowed_set, blocked_set=blocked_set):
            continue
        title = html.unescape(re.sub(r"<.*?>", "", title_html)).strip()
        results.append({"title": title, "url": url2, "content": None, "source": "duckduckgo"})
        if len(results) >= max_results:
            break
    return results


@dataclass(frozen=True, slots=True)
class WebSearchTool(Tool):
    name: str = "WebSearch"
    description: str = "Search the web (Tavily backend; falls back to DuckDuckGo HTML when TAVILY_API_KEY is missing)."
    transport: SearchTransport = _default_search_transport
    endpoint: str = "https://api.tavily.com/search"

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query:
            raise ValueError("WebSearch: 'query' must be a non-empty string")
        max_results = tool_input.get("max_results", 5)
        if not isinstance(max_results, int) or max_results <= 0:
            raise ValueError("WebSearch: 'max_results' must be a positive integer")

        allowed_domains = tool_input.get("allowed_domains")
        blocked_domains = tool_input.get("blocked_domains")
        if allowed_domains is not None and not isinstance(allowed_domains, list):
            raise ValueError("WebSearch: 'allowed_domains' must be a list of strings")
        if blocked_domains is not None and not isinstance(blocked_domains, list):
            raise ValueError("WebSearch: 'blocked_domains' must be a list of strings")
        allowed_set = {str(d).lower() for d in allowed_domains or []}
        blocked_set = {str(d).lower() for d in blocked_domains or []}

        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            results = _duckduckgo_search(query, max_results=max_results, allowed_set=allowed_set, blocked_set=blocked_set)
            return {"query": query, "results": results, "total_results": len(results)}

        headers = {"content-type": "application/json"}
        payload = {"api_key": api_key, "query": query, "max_results": max_results}
        obj = self.transport(self.endpoint, headers, payload)
        results_in = obj.get("results") if isinstance(obj, dict) else None

        results: list[dict[str, Any]] = []
        if isinstance(results_in, list):
            for r in results_in:
                if not isinstance(r, dict):
                    continue
                url = r.get("url")
                if not isinstance(url, str) or not url:
                    continue
                if not _domain_allowed(url=url, allowed_set=allowed_set, blocked_set=blocked_set):
                    continue
                results.append(
                    {
                        "title": r.get("title"),
                        "url": url,
                        "content": r.get("content") or r.get("snippet"),
                        "source": "tavily",
                    }
                )
        return {"query": query, "results": results, "total_results": len(results)}
