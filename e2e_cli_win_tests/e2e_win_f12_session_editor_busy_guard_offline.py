from __future__ import annotations

import json
import sys
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from e2e_cli_win_tests._harness import build_base_env, ensure_conpty_expect_on_syspath, repo_root, temp_project_dir


@contextmanager
def _slow_responses_stub_server():
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != "/responses":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length") or "0")
            _payload = json.loads(self.rfile.read(length).decode("utf-8", errors="replace"))
            raw = f'data: {json.dumps({"type": "response.created", "response": {"id": "resp_1"}})}\n\n'.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()
            time.sleep(0.7)
            self.wfile.write(
                f'data: {json.dumps({"type": "response.output_text.delta", "response_id": "resp_1", "delta": "slow"})}\n\n'.encode(
                    "utf-8"
                )
            )
            self.wfile.flush()
            time.sleep(0.7)
            self.wfile.write(
                f'data: {json.dumps({"type": "response.completed", "response": {"id": "resp_1", "usage": {"total_tokens": 1}}})}\n\n'.encode(
                    "utf-8"
                )
            )
            self.wfile.flush()

        def log_message(self, format, *args):  # noqa: A002,ANN001
            _ = (format, args)
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5.0)


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestWinF12SessionEditorBusyGuardOffline(unittest.TestCase):
    def test_f12_during_streaming_does_not_open_editor(self) -> None:
        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        token = uuid.uuid4().hex

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"
            env = build_base_env(root=root, home_dir=home_dir)
            env["OA_CLI_INPUT_BACKEND"] = "prompt_toolkit"
            env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
            env.pop("RIGHTCODE_API_KEY", None)
            env.pop("NO_COLOR", None)

            with _slow_responses_stub_server() as base_url:
                (project_dir / "opencode.json").write_text(
                    json.dumps(
                        {
                            "provider": {
                                "stub": {
                                    "options": {
                                        "baseURL": base_url,
                                        "apiKey": "stub-key",
                                    }
                                }
                            },
                            "model": "stub/test-model",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                p = spawn(
                    [sys.executable, "-m", "openagentic_cli", "chat"],
                    cwd=str(project_dir),
                    env=env,
                    timeout=240.0,
                    strip_ansi_codes=True,
                )
                try:
                    self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)
                    p.sendline(f"SLOW({token})")
                    self.assertEqual(p.expect(["slow", TIMEOUT, EOF], timeout=30.0), 0)

                    p.send("\x1b[24~")
                    self.assertEqual(p.expect(["Session Editor", "• Done", TIMEOUT, EOF], timeout=10.0), 1)
                    self.assertEqual(p.expect(["Session Editor", "oa>", TIMEOUT, EOF], timeout=30.0), 1)

                    p.sendline("/exit")
                    self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
                finally:
                    rc = p.close(force=bool(p.isalive()))
                self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
