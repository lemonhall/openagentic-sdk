from __future__ import annotations

import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from openagentic_sdk.server.cluster_chat_client import ClusterChatClient

_DEFAULT_K3D_WSL_USER = "lemonhall"
_DEFAULT_SERVICE = "oa-cluster-chat-host"
_DEFAULT_REMOTE_PORT = 8766
_DEFAULT_READY_TIMEOUT_S = 30.0
_DEFAULT_CLUSTER_NAME = "v56-openagentic"
_MAX_HEALTH_FAILURES_BEFORE_RECOVERY = 4
_DEFAULT_ROLLOUT_RETRY_WINDOW_S = 240.0
_DEFAULT_ROLLOUT_CHECK_TIMEOUT_S = 15.0


@dataclass(frozen=True, slots=True)
class K3dChatTarget:
    mode: str
    namespace: str
    service: str
    local_port: int
    remote_port: int
    wsl_user: str

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"


def resolve_k3d_chat_target(*, mode: str, local_port: int | None = None) -> K3dChatTarget:
    mode_name = str(mode or "").strip().lower()
    if mode_name == "real":
        namespace = "openagentic-v56-real"
    elif mode_name == "smoke":
        namespace = "openagentic-v56"
    else:
        raise ValueError(f"unsupported k3d chat mode: {mode!r}")
    port = int(local_port or 0) or _pick_free_local_port()
    return K3dChatTarget(
        mode=mode_name,
        namespace=namespace,
        service=_DEFAULT_SERVICE,
        local_port=port,
        remote_port=_DEFAULT_REMOTE_PORT,
        wsl_user=os.getenv("OA_K3D_WSL_USER", _DEFAULT_K3D_WSL_USER),
    )


def build_port_forward_command(target: K3dChatTarget) -> list[str]:
    kubectl = (
        f'kubectl -n {target.namespace} port-forward service/{target.service} '
        f"{target.local_port}:{target.remote_port}"
    )
    return ["wsl", "-u", "root", "-e", "bash", "-lc", f'su - {target.wsl_user} -c "{kubectl}"']


def build_cluster_start_command(target: K3dChatTarget) -> list[str]:
    _ = target
    cluster_name = os.getenv("OA_K3D_CLUSTER_NAME", _DEFAULT_CLUSTER_NAME)
    return ["wsl", "-u", "root", "-e", "bash", "-lc", f"k3d cluster start {cluster_name}"]


def build_rollout_status_command(target: K3dChatTarget, *, timeout_s: float) -> list[str]:
    timeout = max(1, int(timeout_s))
    kubectl = (
        f'kubectl -n {target.namespace} rollout status deployment/{target.service} '
        f"--timeout={timeout}s"
    )
    return ["wsl", "-u", "root", "-e", "bash", "-lc", f'su - {target.wsl_user} -c "{kubectl}"']


def default_health_probe(base_url: str) -> Mapping[str, Any]:
    return ClusterChatClient(base_url=base_url, timeout_s=2.0).health()


def _default_run_command(argv: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
    timeout = max(1, int(timeout_s))
    return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)


class ManagedK3dChatPortForward:
    def __init__(
        self,
        *,
        target: K3dChatTarget,
        spawn: Callable[[list[str]], subprocess.Popen[str]] | None = None,
        health_probe: Callable[[str], Mapping[str, Any]] | None = None,
        run_command: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        sleep: Callable[[float], None] | None = None,
        ready_timeout_s: float = _DEFAULT_READY_TIMEOUT_S,
    ) -> None:
        self._target = target
        self._spawn = spawn or _default_spawn
        self._health_probe = health_probe or default_health_probe
        self._run_command = run_command or _default_run_command
        self._sleep = sleep or time.sleep
        self._ready_timeout_s = float(ready_timeout_s)
        self._proc: subprocess.Popen[str] | None = None
        self._health: Mapping[str, Any] | None = None
        self._cluster_start_attempted = False

    @property
    def base_url(self) -> str:
        return self._target.base_url

    @property
    def health(self) -> Mapping[str, Any] | None:
        return self._health

    def start(self) -> Mapping[str, Any]:
        if self._proc is not None:
            return self._health or {}
        deadline = time.time() + self._ready_timeout_s
        last_output = ""
        while time.time() < deadline:
            self._proc = self._spawn(build_port_forward_command(self._target))
            health_failures = 0
            while time.time() < deadline:
                proc = self._proc
                assert proc is not None
                if proc.poll() is not None:
                    output = proc.stdout.read() if proc.stdout is not None else ""
                    last_output = output
                    self._close_dead_process(proc)
                    self._proc = None
                    if _looks_like_kube_api_unavailable(output):
                        self._auto_start_cluster_if_needed()
                        self._wait_for_chat_host_rollout()
                        deadline = time.time() + self._ready_timeout_s
                        break
                    if _looks_like_port_forward_target_unavailable(output):
                        self._wait_for_chat_host_rollout()
                        self._sleep(1.0)
                        break
                    raise RuntimeError(_format_port_forward_start_error(target=self._target, output=output))
                try:
                    self._health = self._health_probe(self.base_url)
                    return self._health
                except Exception:
                    health_failures += 1
                    if health_failures >= _MAX_HEALTH_FAILURES_BEFORE_RECOVERY:
                        self.close()
                        self._auto_start_cluster_if_needed()
                        self._wait_for_chat_host_rollout()
                        deadline = time.time() + self._ready_timeout_s
                        break
                    self._sleep(0.5)
        raise RuntimeError(_format_port_forward_start_error(target=self._target, output=last_output or "k3d port-forward did not become ready in time"))

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        self._health = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
        if proc.stdout is not None:
            proc.stdout.close()

    def __enter__(self) -> ManagedK3dChatPortForward:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        self.close()
        return False

    def _auto_start_cluster_if_needed(self) -> None:
        if self._cluster_start_attempted:
            return
        self._cluster_start_attempted = True
        result = self._run_command(
            build_cluster_start_command(self._target),
            timeout_s=max(self._ready_timeout_s, 120.0),
        )
        if result.returncode == 0:
            return
        text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
        raise RuntimeError(f"failed to auto-start k3d cluster: {text or 'no output'}")

    def _wait_for_chat_host_rollout(self) -> None:
        overall_timeout_s = max(self._ready_timeout_s, _DEFAULT_ROLLOUT_RETRY_WINDOW_S)
        deadline = time.time() + overall_timeout_s
        last_text = ""
        while time.time() < deadline:
            remaining_s = max(1.0, deadline - time.time())
            attempt_timeout_s = min(_DEFAULT_ROLLOUT_CHECK_TIMEOUT_S, remaining_s)
            try:
                result = self._run_command(
                    build_rollout_status_command(self._target, timeout_s=attempt_timeout_s),
                    timeout_s=attempt_timeout_s + 5.0,
                )
            except subprocess.TimeoutExpired as exc:
                last_text = f"rollout status timed out after {int(exc.timeout)}s"
                self._sleep(1.0)
                continue
            if result.returncode == 0:
                return
            text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
            last_text = text or "no output"
            if _looks_like_transient_rollout_unavailable(last_text):
                self._sleep(1.0)
                continue
            raise RuntimeError(f"failed to wait for chat host rollout: {last_text}")
        raise RuntimeError(f"failed to wait for chat host rollout: {last_text or 'timed out waiting for rollout'}")

    @staticmethod
    def _close_dead_process(proc: subprocess.Popen[str]) -> None:
        if proc.stdout is not None:
            proc.stdout.close()


def _default_spawn(argv: list[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _pick_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _format_port_forward_start_error(*, target: K3dChatTarget, output: str) -> str:
    text = str(output or "").strip()
    if f'namespaces "{target.namespace}" not found' in text:
        if target.mode == "real":
            return (
                f"k3d real cluster is not deployed yet (namespace '{target.namespace}' not found).\n"
                "Deploy it from WSL2 first:\n"
                "  cd /mnt/e/development/openagentic-sdk\n"
                "  PYTHONPATH=/mnt/e/development/openagentic-sdk python scripts/apply_v56_real_cluster.py "
                "--remote-config openagentic.remote.json --env-file .openagentic.remote.env "
                "--output-dir .openagentic-rendered --apply"
            )
        return (
            f"k3d smoke cluster is not ready yet (namespace '{target.namespace}' not found).\n"
            "Bring it up from WSL2 first:\n"
            '  cd /mnt/e/development/openagentic-sdk\n'
            '  python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_chat_basic.py" -v'
        )
    return f"k3d port-forward exited early: {text or 'no output'}"


def _looks_like_kube_api_unavailable(output: str) -> bool:
    text = str(output or "").lower()
    patterns = (
        "the connection to the server",
        "unable to connect to the server",
        "connection reset by peer",
        "did you specify the right host or port",
        "eof",
    )
    return any(pattern in text for pattern in patterns)


def _looks_like_port_forward_target_unavailable(output: str) -> bool:
    text = str(output or "").lower()
    return (
        "error forwarding port" in text
        and "connect: connection refused" in text
        and ("lost connection to pod" in text or "connection refused" in text)
    )


def _looks_like_transient_rollout_unavailable(output: str) -> bool:
    text = str(output or "").lower()
    patterns = (
        "apiserver not ready",
        "serviceunavailable",
        "timed out waiting for the condition",
        "context deadline exceeded",
        "client.timeout exceeded while awaiting headers",
    )
    return _looks_like_kube_api_unavailable(text) or any(pattern in text for pattern in patterns)
