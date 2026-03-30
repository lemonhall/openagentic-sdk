from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from ..options import OpenAgenticOptions
from ..permissions.gate import PermissionGate
from ..remote_cluster_config import (
    UnavailableRemoteProvider,
    build_remote_cluster_routing_system_prompt,
    load_remote_cluster_bootstrap,
)
from ..sessions.store import FileSessionStore
from ..tools.defaults import default_tool_registry
from .remote_http import RemoteTaskHttpWorkerServer


def build_remote_http_worker_from_remote_config(
    *,
    repo_root: str,
    session_root: str,
    remote_config_path: str,
    env: dict[str, str] | None = None,
) -> tuple[OpenAgenticOptions, FileSessionStore, dict[str, object]]:
    bootstrap = load_remote_cluster_bootstrap(repo_root=repo_root, config_path=remote_config_path, env=env)
    session_store = FileSessionStore(root_dir=Path(session_root))
    health_status: dict[str, object] = {
        "deployment_mode": "real-model",
        "provider_ready": bootstrap.self_check.provider_ready,
        "provider_profiles": list(bootstrap.provider_profiles),
        "config_source": bootstrap.config_source,
    }
    if bootstrap.self_check.errors:
        health_status["provider_errors"] = list(bootstrap.self_check.errors)
    options = OpenAgenticOptions(
        provider=UnavailableRemoteProvider(),
        model=bootstrap.host_model or "gpt-5.4",
        cwd=repo_root,
        project_dir=repo_root,
        tools=default_tool_registry(),
        permission_gate=PermissionGate(permission_mode="bypass"),
        session_store=session_store,
        setting_sources=["project"],
        system_prompt=build_remote_cluster_routing_system_prompt(bootstrap.agents),
        agents=bootstrap.agents,
    )
    return options, session_store, health_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Long-running HTTP worker for remote Task dispatch")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--session-root", required=True)
    parser.add_argument("--provider-factory", default="")
    parser.add_argument("--remote-config", default="")
    parser.add_argument("--model", default="fake")
    parser.add_argument("--node-name", default="")
    parser.add_argument("--node-name-env", default="")
    args = parser.parse_args(argv)

    node_name = args.node_name
    if not node_name and args.node_name_env:
        node_name = os.environ.get(args.node_name_env, "")
    if not node_name:
        raise SystemExit("remote worker requires --node-name or --node-name-env")

    health_status: dict[str, object] = {}
    if args.remote_config:
        options, session_store, health_status = build_remote_http_worker_from_remote_config(
            repo_root=args.repo_root,
            session_root=args.session_root,
            remote_config_path=args.remote_config,
            env=dict(os.environ),
        )
    else:
        if not args.provider_factory:
            raise SystemExit("remote worker requires --provider-factory or --remote-config")
        provider = _load_factory(args.provider_factory)
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
        health_status=health_status,
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
