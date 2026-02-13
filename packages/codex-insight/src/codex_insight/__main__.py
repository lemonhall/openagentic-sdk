from __future__ import annotations

import argparse

from .app import CodexInsightApp


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codex-insight")
    p.add_argument("--db-path", default="", help="Codex state SQLite path (overrides config auto-discovery)")
    p.add_argument("--sessions-dir", default="", help="Codex sessions dir (overrides config auto-discovery)")
    p.add_argument("--timezone", default="", help="Timezone name, e.g. Asia/Shanghai (overrides config)")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    CodexInsightApp(
        db_path_override=args.db_path or None,
        sessions_dir_override=args.sessions_dir or None,
        timezone_override=args.timezone or None,
    ).run()
