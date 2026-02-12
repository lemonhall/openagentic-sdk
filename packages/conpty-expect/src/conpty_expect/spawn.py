from __future__ import annotations

import codecs
import os
import re
import time
from dataclasses import dataclass
from typing import Any, BinaryIO, Pattern

from conpty_expect._ansi import strip_ansi, strip_ansi_with_index_map
from conpty_expect._debug import DebugTimeline
from conpty_expect._win_conpty import WinConPty, conpty_available
from conpty_expect.errors import EofError, TimeoutError


class _TimeoutSentinel:
    pass


class _EofSentinel:
    pass


TIMEOUT = _TimeoutSentinel()
EOF = _EofSentinel()


def _is_regex(p: Any) -> bool:
    # py>=3.11: re.Pattern exists and is sufficient for our purposes.
    return isinstance(p, re.Pattern)


def _compile_pattern(p: Any, *, encoding: str) -> tuple[str, Pattern[str]] | None:
    if p is TIMEOUT or p is EOF:
        return None
    if isinstance(p, bytes):
        s = p.decode(encoding, errors="replace")
        return (s, re.compile(s))
    if isinstance(p, str):
        return (p, re.compile(p))
    if _is_regex(p):
        return (getattr(p, "pattern", "<pattern>"), p)
    raise TypeError(f"unsupported expect pattern type: {type(p)!r}")


@dataclass
class ExpectResult:
    index: int
    before: str
    after: str
    match: re.Match[str] | None


class Spawn:
    """
    Minimal pexpect-like interface:
    - send / sendline
    - expect(patterns)
    - before / after / match

    Notes:
    - For compatibility with pexpect, string patterns are treated as REGEX (not escaped).
    - v0 is Windows-first: the backend is ConPTY when available.
    """

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        encoding: str = "utf-8",
        cols: int = 120,
        rows: int = 30,
        timeout: float = 30.0,
        strip_ansi_codes: bool = False,
        max_read_bytes: int = 4096,
        logfile: BinaryIO | None = None,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("Spawn (v0) currently supports Windows only.")
        if not conpty_available():
            raise RuntimeError("ConPTY is not available on this Windows version.")

        self._pty = WinConPty(argv, cwd=cwd, env=env, cols=int(cols), rows=int(rows))
        self.pid = self._pty.pid
        self.encoding = encoding
        self.timeout = float(timeout)
        self.strip_ansi_codes = bool(strip_ansi_codes)
        self._max_read_bytes = int(max_read_bytes)
        self._decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace")

        self.before = ""
        self.after = ""
        self.match: re.Match[str] | None = None

        self._buf = ""
        self._logfile = logfile
        self._dbg = DebugTimeline.from_env()
        self._dbg.add(f"spawn pid={self.pid} argv={argv!r}")

    def send(self, s: str) -> None:
        b = s.encode(self.encoding, errors="replace")
        if self._logfile:
            try:
                self._logfile.write(b)
            except Exception:
                pass
        self._pty.send_bytes(b)

    def sendline(self, s: str = "") -> None:
        self.send(s + "\r\n")

    def isalive(self) -> bool:
        return self._pty.poll_exit_code() is None

    def terminate(self) -> None:
        self._pty.terminate()

    def close(self, *, force: bool = False, timeout_s: float = 5.0) -> int:
        if force:
            self.terminate()
        self._pty.wait(timeout_s)
        rc = self._pty.poll_exit_code()
        self._pty.close()
        return int(rc) if rc is not None else 1

    def _read_once(self) -> str:
        raw = self._pty.read_available_bytes(max_bytes=self._max_read_bytes)
        if not raw:
            return ""
        if self._logfile:
            try:
                self._logfile.write(raw)
            except Exception:
                pass
        return str(self._decoder.decode(raw, final=False))

    def expect(self, patterns: Any, timeout: float | None = None) -> int:
        """
        pexpect-like:
        - patterns: str | bytes | re.Pattern | [ ... ] plus TIMEOUT/EOF sentinels
        - returns matched index
        - updates before/after/match
        """
        if timeout is None:
            timeout = self.timeout
        timeout = float(timeout)

        if isinstance(patterns, (str, bytes)) or _is_regex(patterns) or patterns in (TIMEOUT, EOF):
            pattern_list = [patterns]
        else:
            pattern_list = list(patterns)

        compiled: list[tuple[str, Pattern[str]] | None] = [_compile_pattern(p, encoding=self.encoding) for p in pattern_list]

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self.strip_ansi_codes:
                hay, index_map = strip_ansi_with_index_map(self._buf)
            else:
                hay, index_map = self._buf, None
            for i, p in enumerate(pattern_list):
                if p is TIMEOUT:
                    continue
                if p is EOF:
                    continue
                cp = compiled[i]
                if cp is None:
                    continue
                _, rx = cp
                m = rx.search(hay)
                if m:
                    self.match = m
                    self.before = hay[: m.start()]
                    self.after = hay[m.start() : m.end()]
                    # Consume up to end of match (pexpect-like).
                    if index_map is None:
                        consume_end = m.end()
                    else:
                        consume_end = index_map[min(max(0, m.end()), len(index_map) - 1)]
                    if consume_end == 0 and m.end() == 0:
                        raise RuntimeError("expect() matched an empty string; refusing to loop forever")
                    self._buf = self._buf[consume_end:]
                    self._dbg.add(f"expect:match index={i} pattern={getattr(rx,'pattern',None)!r}")
                    return i

            if time.monotonic() >= deadline:
                # TIMEOUT sentinel match
                for i, p in enumerate(pattern_list):
                    if p is TIMEOUT:
                        self.before = hay
                        self.after = ""
                        self.match = None
                        self._dbg.add("expect:TIMEOUT sentinel")
                        return i
                dbg = self._dbg.dump()
                raise TimeoutError(f"timeout waiting for patterns: {pattern_list!r}\n--- tail ---\n{hay[-4000:]}\n--- debug ---\n{dbg}")

            chunk = self._read_once()
            if chunk:
                self._buf += chunk
                continue

            # EOF handling
            rc = self._pty.poll_exit_code()
            if rc is not None:
                # The process may have exited but there can still be buffered output.
                # Do a short drain before declaring EOF, bounded by the overall timeout.
                drain_budget_s = min(0.2, max(0.0, deadline - time.monotonic()))
                if drain_budget_s > 0:
                    drain_deadline = time.monotonic() + drain_budget_s
                    chunk2 = ""
                    while time.monotonic() < drain_deadline:
                        chunk2 = self._read_once()
                        if chunk2:
                            self._buf += chunk2
                            break
                        time.sleep(0.01)
                    if chunk2:
                        continue
                for i, p in enumerate(pattern_list):
                    if p is EOF:
                        self.before = hay
                        self.after = ""
                        self.match = None
                        self._dbg.add(f"expect:EOF sentinel exit_code={rc}")
                        return i
                dbg = self._dbg.dump()
                raise EofError(f"EOF before patterns matched: {pattern_list!r}\n--- tail ---\n{hay[-4000:]}\n--- debug ---\n{dbg}")

            time.sleep(0.01)


def spawn(
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    encoding: str = "utf-8",
    cols: int = 120,
    rows: int = 30,
    timeout: float = 30.0,
    strip_ansi_codes: bool = False,
    max_read_bytes: int = 4096,
) -> Spawn:
    if cwd is None:
        cwd = os.getcwd()
    if env is None:
        env = dict(os.environ)
    return Spawn(
        argv=list(argv),
        cwd=str(cwd),
        env=dict(env),
        encoding=encoding,
        cols=int(cols),
        rows=int(rows),
        timeout=float(timeout),
        strip_ansi_codes=bool(strip_ansi_codes),
        max_read_bytes=int(max_read_bytes),
    )
