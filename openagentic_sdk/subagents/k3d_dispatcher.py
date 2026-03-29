from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import time

from .actor_tracing import ActorTracing
from .remote_http import HttpRemoteTaskDispatcher


class K3dPortForwardRemoteTaskDispatcher:
    def __init__(
        self,
        *,
        namespace: str,
        worker_port: int = 8765,
        kubectl_bin: str = "kubectl",
        pod_label_key: str = "oa.openagentic/node-name",
        timeout_s: float = 30.0,
        http_timeout_s: float = 60.0,
    ) -> None:
        self._namespace = namespace
        self._worker_port = worker_port
        self._kubectl_bin = kubectl_bin
        self._pod_label_key = pod_label_key
        self._timeout_s = timeout_s
        self._http_timeout_s = http_timeout_s
        self._tracing: ActorTracing | None = None

    def bind_actor_tracing(self, tracing: ActorTracing) -> None:
        self._tracing = tracing

    async def dispatch(self, request):
        node_name = request.definition.executor.node_name or ""
        if not node_name:
            raise RuntimeError(f"Agent '{request.agent_name}' requires executor.node_name for k3d dispatch")

        pod_name = await asyncio.to_thread(self._resolve_worker_pod_name, node_name)
        local_port = self._pick_free_local_port()
        proc = subprocess.Popen(
            [
                self._kubectl_bin,
                "-n",
                self._namespace,
                "port-forward",
                f"pod/{pod_name}",
                f"{local_port}:{self._worker_port}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            await asyncio.to_thread(self._wait_for_port_forward, proc, local_port)
            dispatcher_kwargs = {
                "base_url": f"http://127.0.0.1:{local_port}",
                "timeout_s": self._http_timeout_s,
            }
            if self._tracing is not None:
                dispatcher_kwargs["tracing"] = self._tracing
            base_dispatcher = HttpRemoteTaskDispatcher(**dispatcher_kwargs)
            handle = await base_dispatcher.dispatch(request)
        except Exception:
            self._stop_port_forward(proc)
            raise

        async def _envelopes():
            try:
                if handle.envelopes is not None:
                    async for envelope in handle.envelopes:
                        yield envelope
                    return
                async for event in handle.events:
                    yield event
            finally:
                self._stop_port_forward(proc)

        async def _abort() -> None:
            await handle.abort()

        async def _send(envelope) -> None:
            await handle.send(envelope)

        async def _close() -> None:
            try:
                await handle.close()
            finally:
                self._stop_port_forward(proc)

        return request.make_handle(
            child_session_id=handle.child_session_id,
            target_node=handle.target_node,
            git_revision=handle.git_revision,
            worker_execution_id=handle.worker_execution_id,
            envelopes=_envelopes() if handle.envelopes is not None else None,
            events=None if handle.envelopes is not None else _envelopes(),
            sender=_send,
            aborter=_abort,
            closer=_close,
        )

    def _resolve_worker_pod_name(self, node_name: str) -> str:
        proc = subprocess.run(
            [
                self._kubectl_bin,
                "-n",
                self._namespace,
                "get",
                "pods",
                "-l",
                f"{self._pod_label_key}={node_name}",
                "-o",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"kubectl get pods failed for node '{node_name}': {proc.stdout}{proc.stderr}")
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"kubectl get pods returned invalid JSON for node '{node_name}'") from e
        items = obj.get("items")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"No remote worker pod found for node '{node_name}'")
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata")
            status = item.get("status")
            if not isinstance(meta, dict) or not isinstance(status, dict):
                continue
            phase = status.get("phase")
            name = meta.get("name")
            if phase == "Running" and isinstance(name, str) and name:
                return name
        first_meta = items[0].get("metadata") if isinstance(items[0], dict) else None
        first_name = first_meta.get("name") if isinstance(first_meta, dict) else None
        if isinstance(first_name, str) and first_name:
            return first_name
        raise RuntimeError(f"Remote worker pod for node '{node_name}' has no usable name")

    def _wait_for_port_forward(self, proc: subprocess.Popen[str], local_port: int) -> None:
        deadline = time.time() + self._timeout_s
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
        self._stop_port_forward(proc)
        raise RuntimeError("kubectl port-forward did not become ready in time")

    def _stop_port_forward(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)
        if proc.stdout is not None:
            proc.stdout.close()

    def _pick_free_local_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
