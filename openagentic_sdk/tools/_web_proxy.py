from __future__ import annotations

import os
import urllib.request
from typing import Any


def proxy_map_from_env() -> dict[str, str]:
    http_proxy = (
        os.environ.get("OPENAGENTIC_WEB_HTTP_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    ).strip()
    https_proxy = (
        os.environ.get("OPENAGENTIC_WEB_HTTPS_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or ""
    ).strip()
    proxy_map: dict[str, str] = {}
    if http_proxy:
        proxy_map["http"] = http_proxy
    if https_proxy:
        proxy_map["https"] = https_proxy
    return proxy_map


def urlopen_with_proxy(req: Any, *, timeout: float):
    proxy_map = proxy_map_from_env()
    if not proxy_map:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxy_map))
    return opener.open(req, timeout=timeout)
