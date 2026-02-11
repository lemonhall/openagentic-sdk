from __future__ import annotations

import os
import re
import select
import subprocess
import time
from dataclasses import dataclass
from typing import Pattern

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


@dataclass
class PtyResult:
    exit_code: int
    output: str


class PtyProcess:
    def __init__(self, argv: list[str], *, cwd: str, env: dict[str, str]) -> None:
        if os.name == "nt":
            raise RuntimeError("PtyProcess requires a POSIX pty (run under WSL2/Linux/macOS).")
        import pty  # noqa: PLC0415

        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd

        # Disable input echo on the slave side so test expectations don't match
        # back the user's own input (common with PTY-driven CLIs).
        try:
            import termios  # noqa: PLC0415

            attrs = termios.tcgetattr(slave_fd)
            attrs[3] = attrs[3] & ~termios.ECHO
            termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
        except Exception:  # noqa: BLE001
            pass

        self._proc = subprocess.Popen(
            argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            start_new_session=True,
            close_fds=True,
            text=False,
        )
        try:
            os.close(slave_fd)
        except Exception:  # noqa: BLE001
            pass

        self._buf = ""

    @property
    def pid(self) -> int:
        return int(self._proc.pid or 0)

    def send(self, s: str) -> None:
        os.write(self._master_fd, s.encode("utf-8", errors="replace"))

    def _read_some(self, *, timeout_s: float) -> str:
        r, _w, _x = select.select([self._master_fd], [], [], max(0.0, float(timeout_s)))
        if not r:
            return ""
        try:
            data = os.read(self._master_fd, 4096)
        except OSError:
            return ""
        if not data:
            return ""
        return data.decode("utf-8", errors="replace")

    def read_until(
        self,
        pattern: str | Pattern[str],
        *,
        timeout_s: float = 30.0,
        strip_ansi_codes: bool = True,
    ) -> str:
        if isinstance(pattern, str):
            rx: Pattern[str] = re.compile(re.escape(pattern))
        else:
            rx = pattern

        deadline = time.time() + max(0.1, float(timeout_s))
        while True:
            hay = strip_ansi(self._buf) if strip_ansi_codes else self._buf
            if rx.search(hay):
                return hay
            if self._proc.poll() is not None:
                # Drain any remaining output.
                while True:
                    chunk = self._read_some(timeout_s=0.05)
                    if not chunk:
                        break
                    self._buf += chunk
                hay2 = strip_ansi(self._buf) if strip_ansi_codes else self._buf
                if rx.search(hay2):
                    return hay2
                sample = hay2[-4000:]
                raise AssertionError(
                    f"process exited before pattern matched: {rx.pattern}\n"
                    f"exit_code={self._proc.returncode}\n"
                    f"--- tail ---\n{sample}"
                )

            if time.time() >= deadline:
                sample = hay[-4000:]
                raise TimeoutError(f"timeout waiting for pattern: {rx.pattern}\n--- tail ---\n{sample}")

            chunk = self._read_some(timeout_s=0.1)
            if chunk:
                self._buf += chunk

    def close(self, *, timeout_s: float = 10.0) -> PtyResult:
        try:
            exit_code = int(self._proc.wait(timeout=max(0.1, float(timeout_s))))
        except subprocess.TimeoutExpired:
            try:
                self._proc.terminate()
            except Exception:
                pass
            try:
                exit_code = int(self._proc.wait(timeout=2.0))
            except subprocess.TimeoutExpired:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                exit_code = int(self._proc.wait(timeout=2.0))

        # Drain remaining output.
        while True:
            chunk = self._read_some(timeout_s=0.05)
            if not chunk:
                break
            self._buf += chunk

        try:
            os.close(self._master_fd)
        except Exception:
            pass
        return PtyResult(exit_code=exit_code, output=self._buf)
