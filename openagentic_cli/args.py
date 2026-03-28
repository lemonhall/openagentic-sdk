from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oa")
    # OpenCode VSCode extension parity: it invokes `opencode --port <n>`.
    # We support `oa --port <n>` as an alias of `oa serve --port <n>`.
    parser.add_argument("--host", default=None, help="Bind host (alias for `oa serve --host`; used when no subcommand)")
    parser.add_argument("--port", default=None, type=int, help="Bind port (alias for `oa serve --port`; used when no subcommand)")
    sub = parser.add_subparsers(dest="command")

    p_chat = sub.add_parser("chat", help="Start a multi-turn chat REPL")
    p_chat.add_argument("--resume", dest="session_id", default=None, help="Resume an existing session id")
    p_chat.add_argument("--remote-host", default=None, help="Remote cluster chat host base URL (e.g. http://127.0.0.1:8766)")

    p_run = sub.add_parser("run", help="Run a one-shot prompt")
    p_run.add_argument("prompt", help="Prompt text")
    p_run.add_argument("--json", action="store_true", help="Emit JSON output")
    p_run.add_argument("--stream", dest="stream", action="store_true", default=True, help="Stream output")
    p_run.add_argument("--no-stream", dest="stream", action="store_false", help="Disable streaming output")

    p_resume = sub.add_parser("resume", help="Resume an existing session")
    p_resume.add_argument("session_id", help="Session id to resume")
    p_resume.add_argument("--remote-host", default=None, help="Remote cluster chat host base URL (e.g. http://127.0.0.1:8766)")

    p_logs = sub.add_parser("logs", help="Summarize session events")
    p_logs.add_argument("session_id", help="Session id to summarize")
    p_logs.add_argument(
        "--session-root",
        default=None,
        help="Session root directory (default: ~/.openagentic-sdk; env: OPENAGENTIC_SDK_HOME)",
    )

    p_mcp = sub.add_parser("mcp", help="Manage MCP servers and credentials")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_command")

    p_mcp_list = mcp_sub.add_parser("list", help="List MCP servers from config")
    _ = p_mcp_list

    p_mcp_auth = mcp_sub.add_parser("auth", help="Authenticate to a remote MCP server (OAuth by default)")
    p_mcp_auth.add_argument("name", help="MCP server name (key under config.mcp)")
    p_mcp_auth.add_argument("--token", required=False, default=None, help="Bearer token (manual mode; skips OAuth)")
    p_mcp_auth.add_argument(
        "--callback-port",
        required=False,
        default=19876,
        type=int,
        help="OAuth callback port (default: 19876)",
    )

    p_mcp_logout = mcp_sub.add_parser("logout", help="Clear stored credentials for an MCP server")
    p_mcp_logout.add_argument("name", help="MCP server name (key under config.mcp)")

    p_share = sub.add_parser("share", help="Share a session (offline/local by default)")
    p_share.add_argument("session_id", help="Session id to share")
    p_share.add_argument(
        "--session-root",
        default=None,
        help="Session root directory (default: ~/.openagentic-sdk; env: OPENAGENTIC_SDK_HOME)",
    )

    p_unshare = sub.add_parser("unshare", help="Remove a shared session payload")
    p_unshare.add_argument("share_id", help="Share id to remove")

    p_shared = sub.add_parser("shared", help="Print a shared session payload")
    p_shared.add_argument("share_id", help="Share id to fetch")

    p_auth = sub.add_parser("auth", help="Manage provider auth (auth.json)")
    auth_sub = p_auth.add_subparsers(dest="auth_command")

    p_auth_set = auth_sub.add_parser("set", help="Store an API key for a provider")
    p_auth_set.add_argument("provider_id", help="Provider id (e.g. openai, github-copilot, etc)")
    p_auth_set.add_argument("--key", required=True, help="API key")

    p_auth_rm = auth_sub.add_parser("remove", help="Remove stored auth for a provider")
    p_auth_rm.add_argument("provider_id", help="Provider id")

    _ = auth_sub.add_parser("list", help="List providers with stored auth")

    p_serve = sub.add_parser("serve", help="Run the local OpenAgentic HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_serve.add_argument("--port", default=4096, type=int, help="Bind port (default: 4096)")

    _ = sub.add_parser("acp", help="Run an ACP (Agent Client Protocol) stdio server")

    p_gh = sub.add_parser("github", help="GitHub Actions integration")
    gh_sub = p_gh.add_subparsers(dest="github_command")

    p_gh_install = gh_sub.add_parser("install", help="Generate a GitHub Actions workflow")
    p_gh_install.add_argument(
        "--path",
        default=None,
        help="Workflow file path (default: .github/workflows/openagentic.yml)",
    )
    p_gh_install.add_argument("--force", action="store_true", help="Overwrite existing workflow file")

    p_gh_run = gh_sub.add_parser("run", help="Run as a GitHub Actions worker")
    p_gh_run.add_argument("--event-path", default=None, help="Path to GitHub event JSON (default: $GITHUB_EVENT_PATH)")
    p_gh_run.add_argument("--print-prompt", action="store_true", help="Print derived prompt and exit")
    p_gh_run.add_argument("--reply-text", default=None, help="Use this reply text instead of calling the agent")
    p_gh_run.add_argument("--base-url", default=None, help="GitHub API base URL (default: $GITHUB_API_URL or https://api.github.com)")
    p_gh_run.add_argument("--token", default=None, help="GitHub token (default: $GITHUB_TOKEN)")
    p_gh_run.add_argument(
        "--mentions",
        default=None,
        help="Comma-separated mention triggers (default: $MENTIONS or '/opencode,/oc')",
    )

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)
