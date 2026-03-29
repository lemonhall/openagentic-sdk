from __future__ import annotations

import io
import unittest
from unittest import mock


class TestCliK3dMain(unittest.TestCase):
    def test_chat_k3d_real_uses_managed_port_forward(self) -> None:
        import openagentic_cli.__main__ as cli_main

        captured: dict[str, object] = {}

        class _FakeForward:
            base_url = "http://127.0.0.1:28776"

            def start(self):
                return {"ok": True, "deployment_mode": "real-model"}

            def close(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = (exc_type, exc, tb)
                return False

        async def fake_run_chat(options, *, color_config, debug, stdin, stdout):
            captured["remote_chat_base_url"] = options.remote_chat_base_url
            captured["stdin"] = stdin
            captured["stdout"] = stdout
            _ = (color_config, debug)
            return 0

        with (
            mock.patch.object(cli_main.sys, "stdin", io.StringIO("/exit\n")),
            mock.patch.object(cli_main.sys, "stdout", io.StringIO()),
            mock.patch.object(cli_main, "ManagedK3dChatPortForward", return_value=_FakeForward()),
            mock.patch.object(cli_main, "resolve_k3d_chat_target") as resolve_target,
            mock.patch.object(cli_main, "run_chat", side_effect=fake_run_chat),
        ):
            rc = cli_main.main(["chat", "--k3d-real"])

        self.assertEqual(rc, 0)
        self.assertEqual(captured["remote_chat_base_url"], "http://127.0.0.1:28776")
        resolve_target.assert_called_once_with(mode="real")

    def test_k3d_real_missing_namespace_error_is_human_readable(self) -> None:
        from openagentic_cli.k3d_chat import K3dChatTarget, _format_port_forward_start_error

        text = _format_port_forward_start_error(
            target=K3dChatTarget(
                mode="real",
                namespace="openagentic-v56-real",
                service="oa-cluster-chat-host",
                local_port=18776,
                remote_port=8766,
                wsl_user="lemonhall",
            ),
            output='Error from server (NotFound): namespaces "openagentic-v56-real" not found',
        )

        self.assertIn("k3d real cluster is not deployed yet", text)
        self.assertIn("openagentic-v56-real", text)
        self.assertIn("scripts/apply_v56_real_cluster.py", text)
        self.assertIn(".openagentic.remote.env", text)


if __name__ == "__main__":
    unittest.main()
