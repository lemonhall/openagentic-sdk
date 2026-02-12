from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Pattern

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


@dataclass
class PipeResult:
    exit_code: int
    output: str


class PipeProcess:
    def __init__(self, argv: list[str], *, cwd: str, env: dict[str, str]) -> None:
        self._proc = subprocess.Popen(  # noqa: S603
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("Popen did not create pipes for stdin/stdout.")

        self._stdin = self._proc.stdin
        self._stdout = self._proc.stdout

        self._buf = bytearray()
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, name="oa-cli-e2e-pipe-reader", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        while True:
            try:
                read1 = getattr(self._stdout, "read1", None)
                chunk = read1(4096) if callable(read1) else self._stdout.read(4096)
            except Exception:
                return
            if not chunk:
                return
            with self._lock:
                self._buf += chunk

    def send(self, s: str) -> None:
        data = s.encode("utf-8", errors="replace")
        self._stdin.write(data)
        self._stdin.flush()

    def _snapshot_text(self) -> str:
        with self._lock:
            b = bytes(self._buf)
        return b.decode("utf-8", errors="replace")

    def read_until(self, pattern: str | Pattern[str], *, timeout_s: float = 30.0, strip_ansi_codes: bool = True) -> str:
        if isinstance(pattern, str):
            rx: Pattern[str] = re.compile(re.escape(pattern))
        else:
            rx = pattern

        deadline = time.time() + max(0.1, float(timeout_s))
        while True:
            out = self._snapshot_text()
            hay = strip_ansi(out) if strip_ansi_codes else out
            if rx.search(hay):
                return hay

            if time.time() >= deadline:
                sample = hay[-4000:]
                raise TimeoutError(f"timeout waiting for pattern: {rx.pattern}\n--- tail ---\n{sample}")

            rc = self._proc.poll()
            if rc is not None:
                sample = hay[-4000:]
                raise AssertionError(f"process exited before pattern matched: {rx.pattern}\n--- tail ---\n{sample}")

            time.sleep(0.01)

    def close(self, *, timeout_s: float = 10.0) -> PipeResult:
        try:
            rc = self._proc.wait(timeout=max(0.1, float(timeout_s)))
        except subprocess.TimeoutExpired:
            try:
                self.send("/exit\r\n")
            except Exception:
                pass
            try:
                rc = self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
                rc = self._proc.wait(timeout=5.0)

        out = self._snapshot_text()
        try:
            self._stdin.close()
        except Exception:
            pass
        try:
            self._stdout.close()
        except Exception:
            pass
        return PipeResult(exit_code=int(rc), output=out)
