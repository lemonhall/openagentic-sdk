from __future__ import annotations

import json
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from e2e_cli_win_tests._harness import (
    build_base_env,
    ensure_conpty_expect_on_syspath,
    read_events_jsonl,
    repo_root,
    temp_project_dir,
    wait_for_single_session_id,
)


@contextmanager
def _responses_stub_server(*, original_text: str, edited_text: str):
    captures: list[dict] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != "/responses":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8", errors="replace"))
            captures.append(payload)

            inputs = payload.get("input") if isinstance(payload, dict) else None
            texts: list[str] = []
            if isinstance(inputs, list):
                for item in inputs:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content")
                    if isinstance(content, str):
                        texts.append(content)

            last_user = texts[-1] if texts else ""
            if "CHECK_EDIT" in last_user:
                if edited_text in texts:
                    assistant_text = "SAW_EDITED"
                elif original_text in texts:
                    assistant_text = "SAW_ORIGINAL"
                else:
                    assistant_text = "SAW_NOTHING"
            else:
                assistant_text = "TURN_OK"

            raw = (
                f'data: {json.dumps({"type": "response.created", "response": {"id": f"resp_{len(captures)}"}})}\n\n'
                f'data: {json.dumps({"type": "response.output_text.delta", "response_id": f"resp_{len(captures)}", "delta": assistant_text})}\n\n'
                f'data: {json.dumps({"type": "response.completed", "response": {"id": f"resp_{len(captures)}", "usage": {"total_tokens": 1}}})}\n\n'
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()

        def log_message(self, format, *args):  # noqa: A002,ANN001
            _ = (format, args)
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", captures
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5.0)


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestWinF12SessionEditorSaveOffline(unittest.TestCase):
    def test_f12_editor_save_rewrites_session_and_resets_previous_response_id(self) -> None:
        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        token = uuid.uuid4().hex
        original_text = f"EDITME({token}) original"
        edited_text = f"EDITME({token}) edited"
        second_turn = f"CHECK_EDIT({token})"

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"
            env = build_base_env(root=root, home_dir=home_dir)
            env["OA_CLI_INPUT_BACKEND"] = "prompt_toolkit"
            env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
            env.pop("RIGHTCODE_API_KEY", None)
            env.pop("NO_COLOR", None)

            with _responses_stub_server(original_text=original_text, edited_text=edited_text) as (base_url, captures):
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

                    p.sendline(original_text)
                    self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=60.0), 0)
                    self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)

                    p.send("\x1b[24~")
                    self.assertEqual(p.expect(["Session Editor", TIMEOUT, EOF], timeout=10.0), 0)

                    p.send("\x01")  # Ctrl+A
                    p.send("\x0b")  # Ctrl+K
                    p.send(edited_text)
                    p.send("\x13")  # Ctrl+S

                    self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)

                    p.sendline(second_turn)
                    self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=60.0), 0)
                    self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)

                    p.sendline("/exit")
                    self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
                finally:
                    rc = p.close(force=bool(p.isalive()))
                self.assertEqual(rc, 0)

                session_id = wait_for_single_session_id(home_dir, timeout_s=5.0)
                events = read_events_jsonl(home_dir, session_id)
                user_texts = [str(event.get("text", "")) for event in events if event.get("type") == "user.message"]
                self.assertIn(edited_text, user_texts)
                self.assertNotIn(original_text, user_texts)

                self.assertGreaterEqual(len(captures), 2)
                last_payload = captures[-1]
                self.assertNotIn("previous_response_id", last_payload)
                rendered = last_payload.get("input")
                self.assertIsInstance(rendered, list)
                assert isinstance(rendered, list)
                contents = [item.get("content") for item in rendered if isinstance(item, dict)]
                self.assertIn(edited_text, contents)
                self.assertNotIn(original_text, contents)


if __name__ == "__main__":
    unittest.main()
