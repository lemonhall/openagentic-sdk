from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from openagentic_sdk.remote_cluster_config import load_remote_cluster_bootstrap


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


def _render_template(*, template_path: Path, env_block: str) -> str:
    text = template_path.read_text(encoding="utf-8")
    return text.replace("__OA_REMOTE_ENV_BLOCK__", env_block)


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

    env_map = _load_env_file(env_file)
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
    print(f"Provider profiles: {', '.join(bootstrap.provider_profiles)}")

    if args.apply:
        subprocess.run([args.kubectl, "apply", "-f", str(workers_out)], check=True)
        subprocess.run([args.kubectl, "apply", "-f", str(host_out)], check=True)
        print("Applied manifests to cluster.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
