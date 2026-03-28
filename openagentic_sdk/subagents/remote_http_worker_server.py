from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from ..options import OpenAgenticOptions
from ..permissions.gate import PermissionGate
from ..sessions.store import FileSessionStore
from ..tools.defaults import default_tool_registry
from .remote_http import RemoteTaskHttpWorkerServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Long-running HTTP worker for remote Task dispatch")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--session-root", required=True)
    parser.add_argument("--provider-factory", required=True)
    parser.add_argument("--model", default="fake")
    parser.add_argument("--node-name", default="")
    parser.add_argument("--node-name-env", default="")
    args = parser.parse_args(argv)

    provider = _load_factory(args.provider_factory)
    node_name = args.node_name
    if not node_name and args.node_name_env:
        node_name = os.environ.get(args.node_name_env, "")
    if not node_name:
        raise SystemExit("remote worker requires --node-name or --node-name-env")

    session_store = FileSessionStore(root_dir=Path(args.session_root))
    options = OpenAgenticOptions(
        provider=provider,
        model=args.model,
        cwd=args.repo_root,
        project_dir=args.repo_root,
        tools=default_tool_registry(),
        permission_gate=PermissionGate(permission_mode="bypass"),
        session_store=session_store,
    )
    server = RemoteTaskHttpWorkerServer(
        base_options=options,
        session_store=session_store,
        repo_root=args.repo_root,
        node_name=node_name,
        host=args.host,
        port=args.port,
    )
    httpd = server.make_server()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        httpd.server_close()
    return 0


def _load_factory(spec: str):
    module_name, sep, attr_name = spec.partition(":")
    if not module_name or not sep or not attr_name:
        raise SystemExit("--provider-factory must look like package.module:callable")
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name, None)
    if factory is None or not callable(factory):
        raise SystemExit(f"provider factory not found: {spec}")
    return factory()


if __name__ == "__main__":
    raise SystemExit(main())
