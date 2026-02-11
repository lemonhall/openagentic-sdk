from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


class _LineReader:
    def __init__(self, stream) -> None:  # noqa: ANN001
        self._q: queue.Queue[str] = queue.Queue()

        def _bg() -> None:
            try:
                for line in iter(stream.readline, ""):
                    self._q.put(line)
            except ValueError:
                # Stream may be closed while the reader thread is blocked.
                return

        self._t = threading.Thread(target=_bg, daemon=True)
        self._t.start()

    def get(self, timeout_s: float) -> str | None:
        try:
            return self._q.get(timeout=timeout_s)
        except queue.Empty:
            return None


def _send(proc: subprocess.Popen[str], obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    assert "\n" not in line
    stdin = proc.stdin
    if stdin is None:
        raise RuntimeError("process stdin is closed")
    stdin.write(line + "\n")
    stdin.flush()


def _read_json_line(reader: _LineReader, timeout_s: float) -> dict | None:
    line = reader.get(timeout_s)
    if line is None:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def _wait_for_response(
    *,
    proc: subprocess.Popen[str],
    out_reader: _LineReader,
    request_id: int,
    timeout_s: float,
    notifications: list[dict],
    client_requests: list[dict] | None = None,
) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            try:
                err = proc.stderr.read() if proc.stderr is not None else ""
            except Exception:  # noqa: BLE001
                err = ""
            raise RuntimeError(f"process exited early (code={proc.returncode}): {err[-2000:]}")

        msg = _read_json_line(out_reader, timeout_s=max(0.05, deadline - time.time()))
        if msg is None:
            continue

        # Handle server->client requests (e.g. permissions).
        if isinstance(msg, dict) and msg.get("jsonrpc") == "2.0" and isinstance(msg.get("id"), int) and isinstance(msg.get("method"), str):
            if client_requests is not None:
                client_requests.append(msg)
            if msg.get("method") == "session/request_permission":
                rid = int(msg["id"])
                _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": rid,
                        "result": {"outcome": {"outcome": "selected", "optionId": "allow"}},
                    },
                )
                continue
            # Unknown request: reply with method not found.
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": int(msg["id"]),
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )
            continue

        if isinstance(msg, dict) and msg.get("jsonrpc") == "2.0" and msg.get("method") == "session/update":
            notifications.append(msg)
            continue

        if isinstance(msg, dict) and msg.get("jsonrpc") == "2.0" and msg.get("id") == request_id:
            return msg

    raise TimeoutError(f"timed out waiting for response id={request_id}")


class TestAcpStdioProtocol(unittest.TestCase):
    def _run_proc(self, *, cwd: Path, mode: str) -> subprocess.Popen[str]:
        fixture = Path(__file__).resolve().parent / "fixtures" / "acp_stub_agent_server.py"
        self.assertTrue(fixture.exists())

        env = dict(os.environ)
        env["PYTHONPATH"] = os.fspath(_repo_root()) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["ACP_TEST_MODE"] = mode
        return subprocess.Popen(
            [sys.executable, os.fspath(fixture)],
            cwd=os.fspath(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def _init_and_new(self, proc: subprocess.Popen[str], out_reader: _LineReader, cwd: Path) -> str:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1"}})
        init = _wait_for_response(proc=proc, out_reader=out_reader, request_id=1, timeout_s=10.0, notifications=[])
        self.assertIn("result", init)
        self.assertEqual(init.get("result", {}).get("protocolVersion"), "1")

        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": os.fspath(cwd), "mcpServers": []}})
        new = _wait_for_response(proc=proc, out_reader=out_reader, request_id=2, timeout_s=10.0, notifications=[])
        sid = new.get("result", {}).get("sessionId")
        self.assertIsInstance(sid, str)
        self.assertTrue(sid)
        return str(sid)

    def test_initialize_new_and_prompt_streams_updates(self) -> None:
        fixture = Path(__file__).resolve().parent / "fixtures" / "acp_stub_agent_server.py"
        self.assertTrue(fixture.exists())

        with TemporaryDirectory() as td:
            cwd = Path(td)
            proc = self._run_proc(cwd=cwd, mode="ok")
            try:
                assert proc.stdin is not None
                assert proc.stdout is not None
                out_reader = _LineReader(proc.stdout)

                sid = self._init_and_new(proc, out_reader, cwd)

                notes: list[dict] = []
                _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": sid, "prompt": "hi"}})
                resp = _wait_for_response(proc=proc, out_reader=out_reader, request_id=3, timeout_s=5.0, notifications=notes)
                self.assertIn("result", resp)
                self.assertIsInstance(resp.get("result", {}).get("stopReason"), str)
                self.assertTrue(any(n.get("method") == "session/update" for n in notes))
            finally:
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except Exception:
                    pass
                try:
                    if proc.stdout is not None:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def test_permission_requests_are_issued_for_tools(self) -> None:
        with TemporaryDirectory() as td:
            cwd = Path(td)
            proc = self._run_proc(cwd=cwd, mode="permission")
            try:
                assert proc.stdin is not None
                assert proc.stdout is not None
                out_reader = _LineReader(proc.stdout)
                sid = self._init_and_new(proc, out_reader, cwd)

                notes: list[dict] = []
                client_reqs: list[dict] = []
                _send(proc, {"jsonrpc": "2.0", "id": 10, "method": "session/prompt", "params": {"sessionId": sid, "prompt": "hi"}})
                resp = _wait_for_response(
                    proc=proc,
                    out_reader=out_reader,
                    request_id=10,
                    timeout_s=8.0,
                    notifications=notes,
                    client_requests=client_reqs,
                )
                self.assertEqual(resp.get("result", {}).get("stopReason"), "end")
                self.assertTrue(any(r.get("method") == "session/request_permission" for r in client_reqs))
            finally:
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except Exception:
                    pass
                try:
                    if proc.stdout is not None:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def test_session_cancel_causes_cancelled_stop_reason(self) -> None:
        with TemporaryDirectory() as td:
            cwd = Path(td)
            proc = self._run_proc(cwd=cwd, mode="slow")
            try:
                assert proc.stdin is not None
                assert proc.stdout is not None
                out_reader = _LineReader(proc.stdout)
                sid = self._init_and_new(proc, out_reader, cwd)

                _send(proc, {"jsonrpc": "2.0", "id": 20, "method": "session/prompt", "params": {"sessionId": sid, "prompt": "hi"}})
                # Wait for at least one update, then cancel.
                deadline = time.time() + 5.0
                saw_update = False
                while time.time() < deadline:
                    msg = _read_json_line(out_reader, timeout_s=0.25)
                    if msg is None:
                        continue
                    if isinstance(msg, dict) and msg.get("method") == "session/update":
                        saw_update = True
                        break
                self.assertTrue(saw_update)

                _send(proc, {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": sid}})

                # Now wait for the prompt response.
                notes: list[dict] = []
                resp = _wait_for_response(proc=proc, out_reader=out_reader, request_id=20, timeout_s=5.0, notifications=notes)
                self.assertEqual(resp.get("result", {}).get("stopReason"), "cancelled")
            finally:
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except Exception:
                    pass
                try:
                    if proc.stdout is not None:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def test_session_load_replays_history_as_updates(self) -> None:
        with TemporaryDirectory() as td:
            cwd = Path(td)
            proc = self._run_proc(cwd=cwd, mode="ok")
            try:
                assert proc.stdin is not None
                assert proc.stdout is not None
                out_reader = _LineReader(proc.stdout)
                sid = self._init_and_new(proc, out_reader, cwd)

                _send(proc, {"jsonrpc": "2.0", "id": 40, "method": "session/prompt", "params": {"sessionId": sid, "prompt": "hi"}})
                _ = _wait_for_response(proc=proc, out_reader=out_reader, request_id=40, timeout_s=5.0, notifications=[])

                notes: list[dict] = []
                _send(proc, {"jsonrpc": "2.0", "id": 41, "method": "session/load", "params": {"sessionId": sid, "cwd": os.fspath(cwd), "mcpServers": []}})
                resp = _wait_for_response(proc=proc, out_reader=out_reader, request_id=41, timeout_s=5.0, notifications=notes)
                self.assertIn("result", resp)
                self.assertTrue(any(n.get("method") == "session/update" for n in notes))
            finally:
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except Exception:
                    pass
                try:
                    if proc.stdout is not None:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass


if __name__ == "__main__":
    unittest.main()
