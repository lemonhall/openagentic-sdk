from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

CLUSTER_NAME = "v56-openagentic"
NAMESPACE = "openagentic-v56"
WORKER_PORT = 8765
CHAT_HOST_PORT = 8766

SERVER_NODE = f"k3d-{CLUSTER_NAME}-server-0"
AGENT_A_NODE = f"k3d-{CLUSTER_NAME}-agent-0"
AGENT_B_NODE = f"k3d-{CLUSTER_NAME}-agent-1"
WORKER_A_DEPLOYMENT = "oa-remote-worker-agent-0"
WORKER_B_DEPLOYMENT = "oa-remote-worker-agent-1"
CHAT_HOST_DEPLOYMENT = "oa-cluster-chat-host"
CHAT_HOST_SERVICE = "oa-cluster-chat-host"

_READY = False


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def authoritative_repo_root() -> Path:
    return ensure_git_mirror()


def ensure_cluster_ready() -> None:
    global _READY
    if _READY:
        return

    for tool_name in ("docker", "kubectl", "k3d"):
        if shutil.which(tool_name) is None:
            raise unittest.SkipTest(f"missing required tool: {tool_name}")

    desired_head = current_git_head()
    desired_mirror = ensure_git_mirror()

    if _cluster_exists() and _cluster_head() != desired_head:
        _run(["k3d", "cluster", "delete", CLUSTER_NAME], check=False)

    if not _cluster_exists():
        rendered = _render_cluster_config(desired_mirror)
        _run(["k3d", "cluster", "create", "--config", str(rendered)])
        _cluster_head_path().write_text(desired_head, encoding="utf-8")

    _preload_node_images()
    _run(["kubectl", "config", "use-context", f"k3d-{CLUSTER_NAME}"])
    _run(["kubectl", "apply", "-f", str(repo_root() / "deploy" / "k3d" / "v56-workers.yaml")])
    _run(["kubectl", "apply", "-f", str(repo_root() / "deploy" / "k8s" / "v56" / "chat-host.yaml")])
    _run(["kubectl", "-n", NAMESPACE, "rollout", "status", f"deployment/{WORKER_A_DEPLOYMENT}", "--timeout=180s"])
    _run(["kubectl", "-n", NAMESPACE, "rollout", "status", f"deployment/{WORKER_B_DEPLOYMENT}", "--timeout=180s"])
    _run(["kubectl", "-n", NAMESPACE, "rollout", "status", f"deployment/{CHAT_HOST_DEPLOYMENT}", "--timeout=180s"])
    _READY = True


def build_dispatcher():
    from openagentic_sdk.subagents.k3d_dispatcher import K3dPortForwardRemoteTaskDispatcher

    return K3dPortForwardRemoteTaskDispatcher(namespace=NAMESPACE, worker_port=WORKER_PORT)


def current_git_head() -> str:
    proc = _run(["git", "rev-parse", "HEAD"])
    return proc.stdout.strip()


def read_repo_text(rel_path: str) -> str:
    return (authoritative_repo_root() / rel_path).read_text(encoding="utf-8")


@contextmanager
def port_forward_chat_host():
    local_port = _pick_free_local_port()
    proc = subprocess.Popen(
        [
            "kubectl",
            "-n",
            NAMESPACE,
            "port-forward",
            f"service/{CHAT_HOST_SERVICE}",
            f"{local_port}:{CHAT_HOST_PORT}",
        ],
        cwd=repo_root(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_port_forward(proc, local_port)
        yield f"http://127.0.0.1:{local_port}"
    finally:
        _stop_port_forward(proc)


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


def _render_cluster_config(mirror_root: Path) -> Path:
    template_path = repo_root() / "deploy" / "k3d" / "v56-cluster.yaml"
    rendered_path = Path(tempfile.gettempdir()) / "openagentic-v56-cluster.yaml"
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("__OA_REPO_ROOT__", str(mirror_root))
    rendered_path.write_text(text, encoding="utf-8")
    return rendered_path


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=repo_root(), check=check, capture_output=True, text=True)


def _preload_node_images() -> None:
    pause_tar = Path(tempfile.gettempdir()) / "openagentic-v56-pause-amd64.tar"
    python_tar = Path(tempfile.gettempdir()) / "openagentic-v56-python312-amd64.tar"

    _ensure_image_present("rancher/mirrored-pause:3.6")
    _ensure_image_present("python:3.12-slim")
    _run(["docker", "image", "save", "--platform", "linux/amd64", "rancher/mirrored-pause:3.6", "-o", str(pause_tar)])
    _run(["docker", "image", "save", "--platform", "linux/amd64", "python:3.12-slim", "-o", str(python_tar)])

    for node_name in (SERVER_NODE, AGENT_A_NODE, AGENT_B_NODE):
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


def _ensure_image_present(image_ref: str) -> None:
    inspect = _run(["docker", "image", "inspect", image_ref], check=False)
    if inspect.returncode == 0:
        return
    _run(["docker", "pull", image_ref])


def ensure_git_mirror() -> Path:
    mirror = _mirror_root_for_head(current_git_head())
    if (mirror / ".git").exists():
        return mirror
    if mirror.exists():
        shutil.rmtree(mirror)
    _run(["git", "clone", "--no-hardlinks", "--no-checkout", str(repo_root()), str(mirror)])
    _run(["git", "-C", str(mirror), "checkout", "--force", current_git_head()])
    return mirror


def _mirror_root_for_head(head: str) -> Path:
    return Path(tempfile.gettempdir()) / f"openagentic-v56-mirror-{head[:12]}"


def _cluster_head() -> str:
    path = _cluster_head_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _cluster_head_path() -> Path:
    return Path(tempfile.gettempdir()) / "openagentic-v56-cluster-head.txt"


def _pick_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port_forward(proc: subprocess.Popen[str], local_port: int) -> None:
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if proc.poll() is not None:
            output = ""
            if proc.stdout is not None:
                output = proc.stdout.read()
            raise RuntimeError(f"kubectl port-forward exited early: {output}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", local_port)) == 0:
                return
        time.sleep(0.1)
    _stop_port_forward(proc)
    raise RuntimeError("kubectl port-forward did not become ready in time")


def _stop_port_forward(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
    if proc.stdout is not None:
        proc.stdout.close()
