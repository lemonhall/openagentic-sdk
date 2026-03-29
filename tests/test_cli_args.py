import unittest
from contextlib import redirect_stdout
from io import StringIO


class TestCliArgs(unittest.TestCase):
    def test_resume_parses_session_id(self) -> None:
        from openagentic_cli.args import parse_args

        ns = parse_args(["resume", "abc123"])
        self.assertEqual(ns.command, "resume")
        self.assertEqual(ns.session_id, "abc123")

    def test_root_help_mentions_chat_examples(self) -> None:
        from openagentic_cli.args import build_parser

        text = build_parser().format_help()
        self.assertIn("oa chat --help", text)
        self.assertIn("oa chat --k3d-real", text)

    def test_global_version_flag_prints_version(self) -> None:
        from openagentic_cli import __version__
        from openagentic_cli.args import build_parser

        stdout = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stdout(stdout):
                build_parser().parse_args(["--version"])

        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"oa {__version__}")


if __name__ == "__main__":
    unittest.main()
