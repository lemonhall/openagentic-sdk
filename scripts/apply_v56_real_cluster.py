from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from openagentic_sdk.remote_cluster_config import load_remote_cluster_bootstrap


_K3D_PROXY_HOSTNAME = "host.k3d.internal"
_DEFAULT_K3D_GATEWAY_CONTAINER = "k3d-v56-openagentic-server-0"
_RUNTIME_WHEELHOUSE_DIR = ".openagentic-wheelhouse"
_RUNTIME_REQUIREMENTS: tuple[str, ...] = (
    "protobuf<6",
    "opentelemetry-api<2",
    "opentelemetry-sdk<2",
    "opentelemetry-exporter-otlp-proto-http<2",
)
_PROXY_SCOPE_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("HTTP_PROXY", "http_proxy"), "OPENAGENTIC_WEB_HTTP_PROXY"),
    (("HTTPS_PROXY", "https_proxy"), "OPENAGENTIC_WEB_HTTPS_PROXY"),
    (("NO_PROXY", "no_proxy"), "OPENAGENTIC_WEB_NO_PROXY"),
)


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not key or not sep:
            raise SystemExit(f"Invalid env line in {path}: {raw_line!r}")
        env[key] = value.strip()
    return env


def _render_env_block(env_map: dict[str, str]) -> str:
    lines: list[str] = []
    for key in sorted(env_map):
        value = env_map[key]
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f"            - name: {key}")
        lines.append(f'              value: "{escaped}"')
    return "\n".join(lines)


def _rewrite_proxy_url_host(value: str, *, gateway_ip: str) -> str:
    parts = urlsplit(value)
    hostname = parts.hostname
    if not hostname or hostname.lower() != _K3D_PROXY_HOSTNAME:
        return value
    netloc = gateway_ip
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    if parts.username:
        credentials = parts.username
        if parts.password:
            credentials = f"{credentials}:{parts.password}"
        netloc = f"{credentials}@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _rewrite_k3d_proxy_hosts(env_map: dict[str, str], *, gateway_ip: str) -> dict[str, str]:
    rewritten = dict(env_map)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        value = rewritten.get(key)
        if isinstance(value, str) and value.strip():
            rewritten[key] = _rewrite_proxy_url_host(value, gateway_ip=gateway_ip)
    return rewritten


def _discover_k3d_gateway_ip() -> str | None:
    override = os.environ.get("OA_K3D_PROXY_GATEWAY_IP", "").strip()
    if override:
        return override
    container_name = os.environ.get("OA_K3D_GATEWAY_CONTAINER", _DEFAULT_K3D_GATEWAY_CONTAINER).strip()
    if not container_name:
        return None
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "sh",
                "-lc",
                "ip route | awk '/default/ {print $3; exit}'",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    gateway_ip = proc.stdout.strip()
    return gateway_ip or None


def _prepare_env_map(env_map: dict[str, str]) -> dict[str, str]:
    proxy_values = [
        env_map.get("HTTP_PROXY", ""),
        env_map.get("HTTPS_PROXY", ""),
        env_map.get("http_proxy", ""),
        env_map.get("https_proxy", ""),
    ]
    if not any(_K3D_PROXY_HOSTNAME in str(value) for value in proxy_values):
        return env_map
    gateway_ip = _discover_k3d_gateway_ip()
    if not gateway_ip:
        return env_map
    return _rewrite_k3d_proxy_hosts(env_map, gateway_ip=gateway_ip)


def _scope_web_proxy_env(env_map: dict[str, str]) -> dict[str, str]:
    scoped = dict(env_map)
    for source_keys, target_key in _PROXY_SCOPE_MAP:
        value = ""
        for key in source_keys:
            candidate = str(scoped.get(key, "") or "").strip()
            if candidate:
                value = candidate
                break
        if value:
            scoped[target_key] = value
        for key in source_keys:
            scoped.pop(key, None)
    return scoped


def _render_template(*, template_path: Path, env_block: str) -> str:
    text = template_path.read_text(encoding="utf-8")
    return text.replace("__OA_REMOTE_ENV_BLOCK__", env_block)


def _authoritative_repo_root() -> Path:
    from e2e_k3d_tests._harness import authoritative_repo_root

    return authoritative_repo_root()


def _runtime_requirements_text() -> str:
    return "".join(f"{item}\n" for item in _RUNTIME_REQUIREMENTS)


def _ensure_runtime_wheelhouse() -> Path:
    mirror_root = _authoritative_repo_root()
    wheelhouse = mirror_root / _RUNTIME_WHEELHOUSE_DIR
    marker_path = wheelhouse / ".requirements.txt"
    expected_marker = _runtime_requirements_text()
    if marker_path.exists() and marker_path.read_text(encoding="utf-8") == expected_marker and any(wheelhouse.iterdir()):
        return wheelhouse
    if wheelhouse.exists():
        shutil.rmtree(wheelhouse)
    wheelhouse.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--dest",
            str(wheelhouse),
            *_RUNTIME_REQUIREMENTS,
        ],
        check=True,
        env=os.environ.copy(),
    )
    marker_path.write_text(expected_marker, encoding="utf-8", newline="\n")
    return wheelhouse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render/apply v56 real-model cluster manifests")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--remote-config", default="openagentic.remote.json")
    parser.add_argument("--env-file", default=".openagentic.remote.env")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    remote_config = Path(args.remote_config)
    if not remote_config.is_absolute():
        remote_config = (repo_root / remote_config).resolve()
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (repo_root / env_file).resolve()

    env_map = _scope_web_proxy_env(_prepare_env_map(_load_env_file(env_file)))
    bootstrap = load_remote_cluster_bootstrap(repo_root=repo_root, config_path=remote_config, env=env_map)
    if not bootstrap.self_check.provider_ready:
        raise SystemExit("Remote cluster config self-check failed:\n- " + "\n- ".join(bootstrap.self_check.errors))

    wheelhouse = _ensure_runtime_wheelhouse()
    env_block = _render_env_block(env_map)
    worker_text = _render_template(
        template_path=repo_root / "deploy" / "k3d" / "v56-workers-real.template.yaml",
        env_block=env_block,
    )
    host_text = _render_template(
        template_path=repo_root / "deploy" / "k8s" / "v56" / "chat-host-real.template.yaml",
        env_block=env_block,
    )

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="openagentic-v56-real-"))
    workers_out = output_dir / "v56-workers-real.yaml"
    host_out = output_dir / "chat-host-real.yaml"
    workers_out.write_text(worker_text, encoding="utf-8", newline="\n")
    host_out.write_text(host_text, encoding="utf-8", newline="\n")

    print(f"Rendered: {workers_out}")
    print(f"Rendered: {host_out}")
    print(f"Config: {remote_config}")
    print(f"Wheelhouse: {wheelhouse}")
    print(f"Provider profiles: {', '.join(bootstrap.provider_profiles)}")

    if args.apply:
        subprocess.run([args.kubectl, "apply", "-f", str(workers_out)], check=True)
        subprocess.run([args.kubectl, "apply", "-f", str(host_out)], check=True)
        print("Applied manifests to cluster.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
