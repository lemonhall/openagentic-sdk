from __future__ import annotations

import os
import sys
import unittest
import uuid

from _bootstrap import ensure_src_on_syspath

ensure_src_on_syspath()

from conpty_expect.spawn import EOF, TIMEOUT, spawn


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestUnittestBasic(unittest.TestCase):
    def _utf8_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def test_expect_matches_and_consumes_buffer(self) -> None:
        token = f"CE_UNIT_{uuid.uuid4().hex}"
        p = spawn(["cmd.exe", "/c", "echo", token], env=dict(os.environ))
        try:
            idx = p.expect([token, TIMEOUT, EOF], timeout=5.0)
            self.assertEqual(idx, 0)
            self.assertIn(token, p.after)
        finally:
            p.close(force=True)

    def test_timeout_sentinel(self) -> None:
        p = spawn([sys.executable, "-u", "-c", "import time; time.sleep(5)"], env=self._utf8_env())
        try:
            idx = p.expect(["NEVER_MATCH", TIMEOUT, EOF], timeout=0.2)
            self.assertEqual(idx, 1)
        finally:
            p.close(force=True)

    def test_eof_sentinel(self) -> None:
        p = spawn([sys.executable, "-u", "-c", "print('hi')"], env=self._utf8_env())
        try:
            idx = p.expect([EOF], timeout=5.0)
            self.assertEqual(idx, 0)
            self.assertIn("hi", p.before)
        finally:
            p.close(force=True)

    def test_strip_ansi_consumes_correctly(self) -> None:
        script = (
            "import sys; "
            "sys.stdout.write('\\x1b[31mRED\\x1b[0mTAIL\\n'); "
            "sys.stdout.flush()"
        )
        p = spawn([sys.executable, "-u", "-c", script], env=self._utf8_env(), strip_ansi_codes=True)
        try:
            self.assertEqual(p.expect(["RED", TIMEOUT, EOF], timeout=5.0), 0)
            self.assertEqual(p.expect(["TAIL", TIMEOUT, EOF], timeout=5.0), 0)
        finally:
            p.close(force=True)

    def test_incremental_decoder_handles_split_multibyte(self) -> None:
        token = "你好世界"
        script = f"import sys; sys.stdout.write({token!r}); sys.stdout.flush()"
        p = spawn(
            [sys.executable, "-u", "-c", script],
            env=self._utf8_env(),
            encoding="utf-8",
            max_read_bytes=1,
        )
        try:
            self.assertEqual(p.expect(["你好", TIMEOUT, EOF], timeout=5.0), 0)
        finally:
            p.close(force=True)
