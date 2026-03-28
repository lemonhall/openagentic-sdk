from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

CLUSTER_NAME = "v56-openagentic"
NAMESPACE = "openagentic-v56"
WORKER_PORT = 8765

SERVER_NODE = f"k3d-{CLUSTER_NAME}-server-0"
AGENT_A_NODE = f"k3d-{CLUSTER_NAME}-agent-0"
AGENT_B_NODE = f"k3d-{CLUSTER_NAME}-agent-1"
WORKER_A_DEPLOYMENT = "oa-remote-worker-agent-0"
WORKER_B_DEPLOYMENT = "oa-remote-worker-agent-1"

_READY = False


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_cluster_ready() -> None:
    global _READY
    if _READY:
        return

    for tool_name in ("docker", "kubectl", "k3d"):
        if shutil.which(tool_name) is None:
            raise unittest.SkipTest(f"missing required tool: {tool_name}")

    if not _cluster_exists():
        rendered = _render_cluster_config()
        _run(["k3d", "cluster", "create", "--config", str(rendered)])

    _preload_node_images()
    _run(["kubectl", "config", "use-context", f"k3d-{CLUSTER_NAME}"])
    _run(["kubectl", "apply", "-f", str(repo_root() / "deploy" / "k3d" / "v56-workers.yaml")])
    _run(["kubectl", "-n", NAMESPACE, "rollout", "status", f"deployment/{WORKER_A_DEPLOYMENT}", "--timeout=180s"])
    _run(["kubectl", "-n", NAMESPACE, "rollout", "status", f"deployment/{WORKER_B_DEPLOYMENT}", "--timeout=180s"])
    _READY = True


def build_dispatcher():
    from openagentic_sdk.subagents.k3d_dispatcher import K3dPortForwardRemoteTaskDispatcher

    return K3dPortForwardRemoteTaskDispatcher(namespace=NAMESPACE, worker_port=WORKER_PORT)


def current_git_head() -> str:
    proc = _run(["git", "rev-parse", "HEAD"])
    return proc.stdout.strip()


def read_repo_text(rel_path: str) -> str:
    return (repo_root() / rel_path).read_text(encoding="utf-8")


def _cluster_exists() -> bool:
    proc = _run(["k3d", "cluster", "list"], check=False)
    if proc.returncode != 0:
        return False
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("NAME"):
            continue
        name = line.split()[0]
        if name == CLUSTER_NAME:
            return True
    return False


def _render_cluster_config() -> Path:
    template_path = repo_root() / "deploy" / "k3d" / "v56-cluster.yaml"
    rendered_path = Path(tempfile.gettempdir()) / "openagentic-v56-cluster.yaml"
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("__OA_REPO_ROOT__", str(repo_root()))
    rendered_path.write_text(text, encoding="utf-8")
    return rendered_path


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=repo_root(), check=check, capture_output=True, text=True)


def _preload_node_images() -> None:
    pause_tar = Path(tempfile.gettempdir()) / "openagentic-v56-pause-amd64.tar"
    python_tar = Path(tempfile.gettempdir()) / "openagentic-v56-python312-amd64.tar"

    _run(["docker", "pull", "rancher/mirrored-pause:3.6"])
    _run(["docker", "pull", "python:3.12-slim"])
    _run(["docker", "image", "save", "--platform", "linux/amd64", "rancher/mirrored-pause:3.6", "-o", str(pause_tar)])
    _run(["docker", "image", "save", "--platform", "linux/amd64", "python:3.12-slim", "-o", str(python_tar)])

    for node_name in (AGENT_A_NODE, AGENT_B_NODE):
        _import_image(
            node_name=node_name,
            tar_path=pause_tar,
            remote_tar_path="/tmp/pause-amd64.tar",
            expected_ref="docker.io/rancher/mirrored-pause:3.6",
        )
        _import_image(
            node_name=node_name,
            tar_path=python_tar,
            remote_tar_path="/tmp/python312-amd64.tar",
            expected_ref="docker.io/library/python:3.12-slim",
        )


def _import_image(*, node_name: str, tar_path: Path, remote_tar_path: str, expected_ref: str) -> None:
    _run(["docker", "cp", str(tar_path), f"{node_name}:{remote_tar_path}"])
    _run(["docker", "exec", node_name, "ctr", "-n", "k8s.io", "images", "import", remote_tar_path], check=False)
    images = _run(["docker", "exec", node_name, "ctr", "-n", "k8s.io", "images", "ls"], check=False)
    if expected_ref not in images.stdout:
        raise RuntimeError(f"Failed to preload image '{expected_ref}' into node '{node_name}'")
