from __future__ import annotations

from importlib import import_module

__all__ = ["OpenAgenticHttpServer", "serve_http", "ClusterChatClient", "ClusterChatRuntime", "ClusterChatHostServer"]


def __getattr__(name: str):
    if name in {"ClusterChatClient", "ClusterChatRuntime"}:
        module = import_module(".cluster_chat_client", __name__)
    elif name == "ClusterChatHostServer":
        module = import_module(".cluster_chat_host", __name__)
    elif name in {"OpenAgenticHttpServer", "serve_http"}:
        module = import_module(".http_server", __name__)
    else:
        raise AttributeError(name)
    value = getattr(module, name)
    globals()[name] = value
    return value
