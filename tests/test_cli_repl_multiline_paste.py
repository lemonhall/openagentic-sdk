import io
import os
import unittest
from unittest import mock


class TestCliReplMultilinePaste(unittest.TestCase):
    def test_read_turn_single_line(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        turn = read_repl_turn(io.StringIO("hello\n"))
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "hello")
        self.assertFalse(turn.is_paste)

    def test_read_turn_bracketed_paste_multiple_lines(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        s = "\x1b[200~a\n" "b\n" "c\x1b[201~\n"
        turn = read_repl_turn(io.StringIO(s))
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "a\nb\nc")
        self.assertTrue(turn.is_paste)

    def test_read_turn_bracketed_paste_same_line(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        s = "\x1b[200~one line\x1b[201~\n"
        turn = read_repl_turn(io.StringIO(s))
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "one line")
        self.assertTrue(turn.is_paste)

    def test_read_turn_paste_does_not_strip_internal_newlines(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        s = "\x1b[200~x\n\n y\x1b[201~\n"
        turn = read_repl_turn(io.StringIO(s))
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "x\n\n y")
        self.assertTrue(turn.is_paste)

    def test_read_turn_manual_paste_mode_until_end(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        stdin = io.StringIO("line1\nline2\n/end\n")
        turn = read_repl_turn(stdin, paste_mode=True)
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "line1\nline2")
        self.assertTrue(turn.is_paste)

    def test_read_turn_manual_paste_mode_strips_bracketed_paste_markers(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        s = "\x1b[200~line1\nline2\x1b[201~\n/end\n"
        turn = read_repl_turn(io.StringIO(s), paste_mode=True)
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "line1\nline2")
        self.assertTrue(turn.is_paste)
        self.assertTrue(turn.is_manual_paste)

    def test_read_turn_manual_paste_mode_end_with_whitespace(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        stdin = io.StringIO("line1\n/end  \n")
        turn = read_repl_turn(stdin, paste_mode=True)
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "line1")
        self.assertTrue(turn.is_paste)
        self.assertTrue(turn.is_manual_paste)

    def test_read_turn_manual_paste_mode_eof_returns_none(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        turn = read_repl_turn(io.StringIO(""), paste_mode=True)
        self.assertIsNone(turn)

    def test_read_turn_manual_paste_mode_eof_after_lines(self) -> None:
        from openagentic_cli.repl import read_repl_turn

        turn = read_repl_turn(io.StringIO("line1\n"), paste_mode=True)
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.text, "line1")
        self.assertTrue(turn.is_paste)
        self.assertTrue(turn.is_manual_paste)

    def test_read_turn_tty_buffered_multiline_coalesces_without_markers(self) -> None:
        if os.name == "nt":
            raise unittest.SkipTest("buffered coalescing heuristic is POSIX-only")

        from openagentic_cli.repl import read_repl_turn

        rfd, wfd = os.pipe()
        try:
            os.write(wfd, b"line1\nline2\nline3\n")
            os.close(wfd)

            with os.fdopen(rfd, "r", encoding="utf-8") as r:
                r.isatty = lambda: True  # type: ignore[method-assign]
                turn = read_repl_turn(r)
                self.assertIsNotNone(turn)
                assert turn is not None
                self.assertEqual(turn.text, "line1\nline2\nline3")
                self.assertTrue(turn.is_paste)
        finally:
            try:
                os.close(wfd)
            except OSError:
                pass
            try:
                os.close(rfd)
            except OSError:
                pass

    def test_disable_posix_echoctl_helper_exists(self) -> None:
        import openagentic_cli.repl as repl

        self.assertTrue(hasattr(repl, "_disable_posix_echoctl"))

    def test_disable_posix_echoctl_clears_echoctl_and_restores(self) -> None:
        import openagentic_cli.repl as repl

        if os.name == "nt":
            raise unittest.SkipTest("termios is not available on Windows")

        import termios  # noqa: PLC0415

        if not hasattr(repl, "_disable_posix_echoctl"):
            self.fail("missing _disable_posix_echoctl")

        class _FakeStdin:
            def isatty(self) -> bool:  # pragma: no cover
                return True

            def fileno(self) -> int:  # pragma: no cover
                return 123

        attrs = [0, 0, 0, termios.ECHOCTL | termios.ECHO, 0, 0, []]
        with mock.patch("termios.tcgetattr", return_value=list(attrs)) as tcgetattr:
            with mock.patch("termios.tcsetattr") as tcsetattr:
                restore = repl._disable_posix_echoctl(_FakeStdin())  # type: ignore[attr-defined]
                self.assertIsNotNone(restore)
                tcgetattr.assert_called_once()
                self.assertGreaterEqual(tcsetattr.call_count, 1)
                set_args, _set_kwargs = tcsetattr.call_args
                self.assertEqual(set_args[0], 123)
                new_attrs = set_args[2]
                self.assertFalse(bool(new_attrs[3] & termios.ECHOCTL))

                assert restore is not None
                restore()
                self.assertEqual(tcsetattr.call_count, 2)
                restore_args, _restore_kwargs = tcsetattr.call_args
                self.assertEqual(restore_args[0], 123)
                self.assertEqual(restore_args[2], attrs)

    def test_run_chat_calls_disable_posix_echoctl_when_tty(self) -> None:
        import asyncio

        import openagentic_cli.repl as repl
        from openagentic_sdk.options import OpenAgenticOptions
        from openagentic_sdk.permissions.gate import PermissionGate

        if not hasattr(repl, "_disable_posix_echoctl"):
            self.fail("missing _disable_posix_echoctl")

        class _FakeProvider:
            name = "fake"

            async def complete(self, **_kwargs):  # pragma: no cover
                raise AssertionError("should not be called")

        class _FakeTty:
            def __init__(self, lines: list[str]) -> None:
                self._lines = lines
                self._writes: list[str] = []

            def isatty(self) -> bool:  # pragma: no cover
                return True

            def readline(self) -> str:  # pragma: no cover
                return self._lines.pop(0) if self._lines else ""

            def write(self, s: str) -> int:  # pragma: no cover
                self._writes.append(s)
                return len(s)

            def flush(self) -> None:  # pragma: no cover
                pass

        stdin = _FakeTty(["n\n"])
        stdout = _FakeTty([])
        opts = OpenAgenticOptions(
            provider=_FakeProvider(),
            model="fake",
            cwd=os.getcwd(),
            permission_gate=PermissionGate(permission_mode="default"),
            setting_sources=[],
        )

        restore = mock.Mock()
        with mock.patch.object(repl, "_disable_posix_echoctl", return_value=restore):  # type: ignore[attr-defined]
            with mock.patch.dict(os.environ, {"OA_CLI_AUTOAPPROVE_PROMPT": "1"}, clear=False):
                rc = asyncio.run(
                    repl.run_chat(opts, color_config=repl.StyleConfig(color="never"), debug=False, stdin=stdin, stdout=stdout)
                )
        self.assertEqual(rc, 0)
        restore.assert_called_once()


if __name__ == "__main__":
    unittest.main()
