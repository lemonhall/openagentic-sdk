import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestMcpAuthStore(unittest.TestCase):
    def test_writes_mcp_auth_with_0600_permissions(self) -> None:
        from openagentic_sdk.mcp.auth_store import McpAuthStore, McpTokens

        with TemporaryDirectory() as td:
            root = Path(td)
            os.environ["OPENAGENTIC_SDK_HOME"] = str(root)
            try:
                store = McpAuthStore.load_default()
                store.update_tokens(
                    "srv",
                    McpTokens(access_token="a", refresh_token="r", expires_at=123.0, scope="mcp:tools"),
                    server_url="https://example/mcp",
                )
                store.save()
                p = store.path
            finally:
                os.environ.pop("OPENAGENTIC_SDK_HOME", None)

            mode = stat.S_IMODE(p.stat().st_mode)
            if os.name == "nt":
                # Windows `chmod` is best-effort and does not provide POSIX mode bits.
                # `stat` typically reports 0o666 for writable files.
                self.assertIn(mode, (0o666, 0o444))
            else:
                self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
