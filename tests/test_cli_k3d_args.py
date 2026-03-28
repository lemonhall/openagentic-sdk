import unittest


class TestCliK3dArgs(unittest.TestCase):
    def test_chat_accepts_k3d_real_flag(self) -> None:
        from openagentic_cli.args import parse_args

        ns = parse_args(["chat", "--k3d-real"])
        self.assertTrue(ns.k3d_real)
        self.assertFalse(ns.k3d_smoke)

    def test_chat_accepts_k3d_smoke_flag(self) -> None:
        from openagentic_cli.args import parse_args

        ns = parse_args(["chat", "--k3d-smoke"])
        self.assertTrue(ns.k3d_smoke)
        self.assertFalse(ns.k3d_real)

    def test_chat_rejects_remote_host_and_k3d_real_together(self) -> None:
        from openagentic_cli.args import parse_args

        with self.assertRaises(SystemExit):
            parse_args(["chat", "--remote-host", "http://127.0.0.1:18776", "--k3d-real"])


if __name__ == "__main__":
    unittest.main()
