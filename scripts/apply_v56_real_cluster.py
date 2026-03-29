from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from openagentic_sdk.remote_cluster_config import load_remote_cluster_bootstrap


_K3D_PROXY_HOSTNAME = "host.k3d.internal"
_DEFAULT_K3D_GATEWAY_CONTAINER = "k3d-v56-openagentic-server-0"
_RUNTIME_IMAGE_REF = "openagentic/python-runtime:v61"
_RUNTIME_DOCKERFILE_RELATIVE = Path("deploy") / "k8s" / "v61" / "openagentic-python-runtime.Dockerfile"
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


def _runtime_dockerfile_path(repo_root: Path) -> Path:
    return repo_root / _RUNTIME_DOCKERFILE_RELATIVE


def _runtime_image_build_command() -> str:
    return f"docker build -f {_RUNTIME_DOCKERFILE_RELATIVE.as_posix()} -t {_RUNTIME_IMAGE_REF} ."


def _ensure_runtime_image_present(repo_root: Path) -> None:
    _ = repo_root
    inspect = subprocess.run(
        ["docker", "image", "inspect", _RUNTIME_IMAGE_REF],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode == 0:
        return
    details = (inspect.stderr or inspect.stdout or "").strip() or "no output"
    raise RuntimeError(
        f"Required local runtime image '{_RUNTIME_IMAGE_REF}' is missing. "
        "Build it in WSL from repo root with: "
        f"{_runtime_image_build_command()} "
        f"docker inspect output: {details}"
    )


def _ensure_runtime_image_preloaded(repo_root: Path) -> Path:
    _ensure_runtime_image_present(repo_root)
    from e2e_k3d_tests import _harness

    tar_path = _harness._ensure_image_archive(_RUNTIME_IMAGE_REF)
    remote_tar_path = f"/tmp/{_harness._image_safe_name(_RUNTIME_IMAGE_REF)}-amd64.tar"
    for node_name in (_harness.SERVER_NODE, _harness.AGENT_A_NODE, _harness.AGENT_B_NODE):
        _harness._import_image(
            node_name=node_name,
            tar_path=tar_path,
            remote_tar_path=remote_tar_path,
            expected_ref=_RUNTIME_IMAGE_REF,
        )
    return tar_path


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
    print(f"Runtime image: {_RUNTIME_IMAGE_REF}")
    print(f"Provider profiles: {', '.join(bootstrap.provider_profiles)}")

    if args.apply:
        _ensure_runtime_image_preloaded(repo_root)
        subprocess.run([args.kubectl, "apply", "-f", str(workers_out)], check=True)
        subprocess.run([args.kubectl, "apply", "-f", str(host_out)], check=True)
        print("Applied manifests to cluster.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
