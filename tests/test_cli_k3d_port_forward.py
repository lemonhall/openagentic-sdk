from __future__ import annotations

import io
import unittest


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


if __name__ == "__main__":
    unittest.main()
