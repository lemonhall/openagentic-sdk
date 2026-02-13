from __future__ import annotations

import os
import sys
import uuid

from _bootstrap import ensure_src_on_syspath

ensure_src_on_syspath()

try:
    import pytest
except Exception:  # noqa: BLE001
    pytest = None

from conpty_expect.spawn import EOF, TIMEOUT, spawn


if pytest is not None:

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_pytest_expect_timeout_sentinel_matches() -> None:
        # A long sleep then we timeout; ensure TIMEOUT sentinel is returned.
        p = spawn(["cmd.exe", "/c", "ping", "127.0.0.1", "-n", "6", ">nul"], env=dict(os.environ))
        try:
            idx = p.expect([TIMEOUT, EOF], timeout=0.2)
            assert idx == 0
        finally:
            p.close(force=True)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_pytest_expect_eof_sentinel_matches() -> None:
        token = f"CE_PY_{uuid.uuid4().hex}"
        p = spawn(["cmd.exe", "/c", "echo", token], env=dict(os.environ))
        try:
            idx = p.expect([re_escape(token), TIMEOUT, EOF], timeout=5.0)
            assert idx == 0
            # consume remainder and then match EOF
            idx2 = p.expect([EOF], timeout=2.0)
            assert idx2 == 0
        finally:
            p.close(force=True)


def re_escape(s: str) -> str:
    # For parity with pexpect (string treated as regex), escape the token to avoid surprises.
    import re

    return re.escape(s)
