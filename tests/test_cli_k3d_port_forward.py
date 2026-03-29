from __future__ import annotations

import io
import subprocess
import unittest
from unittest import mock


class _FakeProc:
    def __init__(self, *, returncode: int | None = None, output: str = "") -> None:
        self._returncode = returncode
        self.stdout = io.StringIO(output)
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True
        self._returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        return 0

    def kill(self) -> None:
        self.killed = True
        self._returncode = -9


class TestCliK3dPortForward(unittest.TestCase):
    def test_default_spawn_detaches_stdin_from_console(self) -> None:
        import subprocess

        from openagentic_cli.k3d_chat import _default_spawn

        with mock.patch("openagentic_cli.k3d_chat.subprocess.Popen") as popen:
            _default_spawn(["wsl", "dummy"])

        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)

    def test_resolve_real_target_uses_real_namespace(self) -> None:
        from openagentic_cli.k3d_chat import resolve_k3d_chat_target

        target = resolve_k3d_chat_target(mode="real", local_port=28776)

        self.assertEqual(target.mode, "real")
        self.assertEqual(target.namespace, "openagentic-v56-real")
        self.assertEqual(target.service, "oa-cluster-chat-host")
        self.assertEqual(target.local_port, 28776)
        self.assertEqual(target.remote_port, 8766)

    def test_build_command_uses_expected_kubectl_port_forward(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, build_port_forward_command

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )

        argv = build_port_forward_command(target)

        self.assertEqual(argv[:5], ["wsl", "-u", "root", "-e", "bash"])
        self.assertIn("openagentic-v56-real", argv[-1])
        self.assertIn("28776:8766", argv[-1])

    def test_start_returns_health_payload_when_probe_succeeds(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        proc = _FakeProc()
        seen: dict[str, object] = {}

        def fake_spawn(argv: list[str]) -> _FakeProc:
            seen["argv"] = argv
            return proc

        def fake_health_probe(base_url: str):
            seen["base_url"] = base_url
            return {"ok": True, "deployment_mode": "real-model"}

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=fake_spawn,
            health_probe=fake_health_probe,
            sleep=lambda _: None,
            ready_timeout_s=0.1,
        )

        payload = forward.start()

        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertEqual(forward.base_url, "http://127.0.0.1:28776")
        self.assertEqual(seen["base_url"], "http://127.0.0.1:28776")
        forward.close()
        self.assertTrue(proc.terminated)

    def test_start_fails_when_process_exits_early(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        proc = _FakeProc(returncode=1, output="bind: address already in use\n")

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=lambda argv: proc,
            health_probe=lambda base_url: {"ok": True},
            sleep=lambda _: None,
            ready_timeout_s=0.1,
        )

        with self.assertRaisesRegex(RuntimeError, "address already in use"):
            forward.start()

    def test_start_auto_starts_cluster_when_kube_api_is_unavailable(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        procs = [
            _FakeProc(returncode=1, output="The connection to the server 0.0.0.0:43636 was refused\n"),
            _FakeProc(),
        ]
        run_calls: list[list[str]] = []

        def fake_spawn(argv: list[str]) -> _FakeProc:
            return procs.pop(0)

        def fake_run(argv: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
            run_calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="started\n", stderr="")

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=fake_spawn,
            health_probe=lambda base_url: {"ok": True, "deployment_mode": "real-model"},
            sleep=lambda _: None,
            ready_timeout_s=0.1,
            run_command=fake_run,
        )

        payload = forward.start()

        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertEqual(len(run_calls), 2)
        self.assertIn("k3d cluster start v56-openagentic", run_calls[0][-1])
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[1][-1])

    def test_start_retries_when_port_forward_hits_transient_pod_connection_refused(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        procs = [
            _FakeProc(
                returncode=1,
                output=(
                    "Forwarding from 127.0.0.1:11242 -> 8766\n"
                    "error forwarding port 8766 to pod: connect: connection refused\n"
                    "error: lost connection to pod\n"
                ),
            ),
            _FakeProc(),
        ]
        run_calls: list[list[str]] = []

        def fake_spawn(argv: list[str]) -> _FakeProc:
            return procs.pop(0)

        def fake_run(argv: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
            run_calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="ready\n", stderr="")

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=fake_spawn,
            health_probe=lambda base_url: {"ok": True, "deployment_mode": "real-model"},
            sleep=lambda _: None,
            ready_timeout_s=0.1,
            run_command=fake_run,
        )

        payload = forward.start()

        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertEqual(len(run_calls), 1)
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[0][-1])

    def test_start_recovers_when_health_probe_stalls_while_process_stays_alive(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        procs = [_FakeProc(), _FakeProc()]
        run_calls: list[list[str]] = []
        health_calls = {"count": 0}

        def fake_spawn(argv: list[str]) -> _FakeProc:
            return procs.pop(0)

        def fake_run(argv: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
            run_calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="ready\n", stderr="")

        def fake_health_probe(base_url: str):
            _ = base_url
            health_calls["count"] += 1
            if health_calls["count"] <= 4:
                raise ConnectionError("health not ready")
            return {"ok": True, "deployment_mode": "real-model"}

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=fake_spawn,
            health_probe=fake_health_probe,
            sleep=lambda _: None,
            ready_timeout_s=0.1,
            run_command=fake_run,
        )

        payload = forward.start()

        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertEqual(len(run_calls), 2)
        self.assertIn("k3d cluster start v56-openagentic", run_calls[0][-1])
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[1][-1])

    def test_start_retries_rollout_wait_when_apiserver_is_temporarily_not_ready(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        procs = [_FakeProc(), _FakeProc()]
        health_calls = {"count": 0}
        run_responses = [
            subprocess.CompletedProcess(["wsl"], 0, stdout="started\n", stderr=""),
            subprocess.CompletedProcess(
                ["wsl"],
                1,
                stdout="Error from server (ServiceUnavailable): apiserver not ready\n",
                stderr="",
            ),
            subprocess.CompletedProcess(["wsl"], 0, stdout="ready\n", stderr=""),
        ]
        run_calls: list[list[str]] = []

        def fake_spawn(argv: list[str]) -> _FakeProc:
            return procs.pop(0)

        def fake_run(argv: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
            _ = timeout_s
            run_calls.append(argv)
            return run_responses.pop(0)

        def fake_health_probe(base_url: str):
            _ = base_url
            health_calls["count"] += 1
            if health_calls["count"] <= 4:
                raise ConnectionError("health not ready")
            return {"ok": True, "deployment_mode": "real-model"}

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=fake_spawn,
            health_probe=fake_health_probe,
            sleep=lambda _: None,
            ready_timeout_s=0.1,
            run_command=fake_run,
        )

        payload = forward.start()

        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertEqual(len(run_calls), 3)
        self.assertIn("k3d cluster start v56-openagentic", run_calls[0][-1])
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[1][-1])
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[2][-1])

    def test_start_retries_rollout_wait_when_rollout_status_times_out_during_cold_boot(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, ManagedK3dChatPortForward

        procs = [_FakeProc(), _FakeProc()]
        health_calls = {"count": 0}
        run_calls: list[list[str]] = []

        def fake_spawn(argv: list[str]) -> _FakeProc:
            return procs.pop(0)

        def fake_run(argv: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
            _ = timeout_s
            run_calls.append(argv)
            if len(run_calls) == 1:
                return subprocess.CompletedProcess(["wsl"], 0, stdout="started\n", stderr="")
            if len(run_calls) == 2:
                raise subprocess.TimeoutExpired(argv, 120)
            return subprocess.CompletedProcess(["wsl"], 0, stdout="ready\n", stderr="")

        def fake_health_probe(base_url: str):
            _ = base_url
            health_calls["count"] += 1
            if health_calls["count"] <= 4:
                raise ConnectionError("health not ready")
            return {"ok": True, "deployment_mode": "real-model"}

        target = K3dChatTarget(
            mode="real",
            namespace="openagentic-v56-real",
            service="oa-cluster-chat-host",
            local_port=28776,
            remote_port=8766,
            wsl_user="lemonhall",
        )
        forward = ManagedK3dChatPortForward(
            target=target,
            spawn=fake_spawn,
            health_probe=fake_health_probe,
            sleep=lambda _: None,
            ready_timeout_s=0.1,
            run_command=fake_run,
        )

        payload = forward.start()

        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertEqual(len(run_calls), 3)
        self.assertIn("k3d cluster start v56-openagentic", run_calls[0][-1])
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[1][-1])
        self.assertIn("rollout status deployment/oa-cluster-chat-host", run_calls[2][-1])


if __name__ == "__main__":
    unittest.main()
