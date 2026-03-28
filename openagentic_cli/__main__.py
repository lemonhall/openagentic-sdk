from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.paths import default_session_root
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.server.http_server import serve_http
from openagentic_sdk.sessions.store import FileSessionStore

from .args import build_parser
from .auth_cmd import cmd_auth_list, cmd_auth_remove, cmd_auth_set
from .config import build_options
from .k3d_chat import ManagedK3dChatPortForward, resolve_k3d_chat_target
from .logs_cmd import summarize_events
from .mcp_cmd import cmd_mcp_auth, cmd_mcp_list, cmd_mcp_logout
from .repl import run_chat
from .run_cmd import run_once
from .share_cmd import cmd_share, cmd_shared, cmd_unshare
from .style import StyleConfig


class _RemoteBridgeProvider:
    name = "remote-chat-bridge"

    async def complete(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        raise AssertionError("remote chat bridge should not call the local provider")


def build_remote_bridge_options(*, cwd: str, project_dir: str | None, resume: str | None, remote_host: str) -> OpenAgenticOptions:
    return OpenAgenticOptions(
        provider=_RemoteBridgeProvider(),
        model="remote-chat-bridge",
        cwd=cwd,
        project_dir=project_dir,
        permission_gate=PermissionGate(permission_mode="bypass"),
        resume=resume,
        remote_chat_base_url=remote_host,
    )


def default_permission_mode() -> str:
    return os.getenv("OA_PERMISSION_MODE") or "default"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    cwd = os.getcwd()
    project_dir = cwd
    permission_mode = default_permission_mode()
    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    style = StyleConfig(color="auto")

    if getattr(ns, "command", None) is None:
        # OpenCode parity: `opencode --port <n>` starts the local server. We
        # accept `oa --port <n>` as an alias of `oa serve --port <n>`.
        port0 = getattr(ns, "port", None)
        if isinstance(port0, int) and port0 > 0:
            host0 = str(getattr(ns, "host", "127.0.0.1") or "127.0.0.1")
            opts = build_options(
                cwd=cwd,
                project_dir=project_dir,
                permission_mode=permission_mode,
                interactive=interactive,
            )
            serve_http(options=opts, host=host0, port=int(port0))
            return 0

        parser.print_help()
        return 0

    if ns.command in ("chat", "resume"):
        session_id = getattr(ns, "session_id", None)
        remote_host = getattr(ns, "remote_host", None)
        k3d_mode = "real" if bool(getattr(ns, "k3d_real", False)) else "smoke" if bool(getattr(ns, "k3d_smoke", False)) else ""
        k3d_forward: ManagedK3dChatPortForward | None = None
        if isinstance(remote_host, str) and remote_host.strip():
            opts = build_remote_bridge_options(
                cwd=cwd,
                project_dir=project_dir,
                resume=session_id,
                remote_host=remote_host.strip(),
            )
        elif k3d_mode:
            target = resolve_k3d_chat_target(mode=k3d_mode)
            k3d_forward = ManagedK3dChatPortForward(target=target)
            k3d_forward.start()
            sys.stdout.write(f"k3d: {k3d_mode} host -> {k3d_forward.base_url}\n")
            sys.stdout.flush()
            opts = build_remote_bridge_options(
                cwd=cwd,
                project_dir=project_dir,
                resume=session_id,
                remote_host=k3d_forward.base_url,
            )
        else:
            opts = build_options(
                cwd=cwd,
                project_dir=project_dir,
                permission_mode=permission_mode,
                resume=session_id,
                interactive=interactive,
            )
        try:
            return int(
                asyncio.run(
                    run_chat(
                        opts,
                        color_config=style,
                        debug=False,
                        stdin=sys.stdin,
                        stdout=sys.stdout,
                    )
                )
            )
        finally:
            if k3d_forward is not None:
                k3d_forward.close()

    if ns.command == "run":
        opts = build_options(
            cwd=cwd,
            project_dir=project_dir,
            permission_mode=permission_mode,
            interactive=interactive,
        )
        prompt = str(getattr(ns, "prompt", "") or "")
        stream = bool(getattr(ns, "stream", True))
        json_output = bool(getattr(ns, "json", False))
        return int(asyncio.run(run_once(opts, prompt, stream=stream, json_output=json_output, color_config=style)))

    if ns.command == "logs":
        root = getattr(ns, "session_root", None)
        if root:
            root_dir = Path(str(root)).expanduser()
        else:
            root_dir = default_session_root()
        store = FileSessionStore(root_dir=root_dir)
        sid = str(getattr(ns, "session_id", "") or "")
        events = store.read_events(sid)
        text = summarize_events(events, color_config=style, isatty=sys.stdout.isatty(), platform=sys.platform)
        sys.stdout.write(text)
        sys.stdout.flush()
        return 0

    if ns.command == "share":
        sid = str(getattr(ns, "session_id", "") or "")
        root = getattr(ns, "session_root", None)
        share_id = cmd_share(session_id=sid, session_root=str(root) if root else None)
        sys.stdout.write(share_id + "\n")
        sys.stdout.flush()
        return 0

    if ns.command == "unshare":
        share_id = str(getattr(ns, "share_id", "") or "")
        sys.stdout.write(cmd_unshare(share_id=share_id) + "\n")
        sys.stdout.flush()
        return 0

    if ns.command == "shared":
        share_id = str(getattr(ns, "share_id", "") or "")
        sys.stdout.write(cmd_shared(share_id=share_id) + "\n")
        sys.stdout.flush()
        return 0

    if ns.command == "mcp":
        sub = getattr(ns, "mcp_command", None)
        if sub == "list":
            sys.stdout.write(cmd_mcp_list(cwd=cwd) + "\n")
            sys.stdout.flush()
            return 0
        if sub == "auth":
            name = str(getattr(ns, "name", "") or "")
            token = getattr(ns, "token", None)
            token2 = str(token) if isinstance(token, str) and token.strip() else None
            callback_port = int(getattr(ns, "callback_port", 19876) or 19876)
            sys.stdout.write(cmd_mcp_auth(cwd=cwd, name=name, token=token2, callback_port=callback_port) + "\n")
            sys.stdout.flush()
            return 0
        if sub == "logout":
            name = str(getattr(ns, "name", "") or "")
            sys.stdout.write(cmd_mcp_logout(name=name) + "\n")
            sys.stdout.flush()
            return 0
        parser.error("missing or unknown mcp subcommand")
        return 2

    if ns.command == "auth":
        sub = getattr(ns, "auth_command", None)
        if sub == "list":
            sys.stdout.write(cmd_auth_list() + "\n")
            sys.stdout.flush()
            return 0
        if sub == "set":
            pid = str(getattr(ns, "provider_id", "") or "")
            key = str(getattr(ns, "key", "") or "")
            sys.stdout.write(cmd_auth_set(provider_id=pid, key=key) + "\n")
            sys.stdout.flush()
            return 0
        if sub == "remove":
            pid = str(getattr(ns, "provider_id", "") or "")
            sys.stdout.write(cmd_auth_remove(provider_id=pid) + "\n")
            sys.stdout.flush()
            return 0
        parser.error("missing or unknown auth subcommand")
        return 2

    if ns.command == "serve":
        host = str(getattr(ns, "host", "127.0.0.1") or "127.0.0.1")
        port = int(getattr(ns, "port", 4096) or 4096)
        opts = build_options(
            cwd=cwd,
            project_dir=project_dir,
            permission_mode=permission_mode,
            interactive=interactive,
        )
        serve_http(options=opts, host=host, port=port)
        return 0

    if ns.command == "acp":
        from openagentic_sdk.integrations.acp_stdio import serve_acp_stdio

        opts = build_options(
            cwd=cwd,
            project_dir=project_dir,
            permission_mode=permission_mode,
            interactive=False,
        )
        asyncio.run(serve_acp_stdio(opts))
        return 0

    if ns.command == "github":
        sub = getattr(ns, "github_command", None)
        if sub == "install":
            from .github_cmd import cmd_github_install

            path = getattr(ns, "path", None)
            force = bool(getattr(ns, "force", False))
            out = cmd_github_install(workflow_path=str(path) if isinstance(path, str) and path else None, force=force)
            sys.stdout.write(out + "\n")
            sys.stdout.flush()
            return 0
        if sub == "run":
            from .github_cmd import cmd_github_run

            event_path = getattr(ns, "event_path", None)
            print_prompt = bool(getattr(ns, "print_prompt", False))
            reply_text = getattr(ns, "reply_text", None)
            base_url = getattr(ns, "base_url", None)
            token = getattr(ns, "token", None)
            mentions = getattr(ns, "mentions", None)
            if isinstance(reply_text, str) and reply_text.strip():
                os.environ["OA_GITHUB_REPLY_TEXT"] = reply_text.strip()
            if isinstance(base_url, str) and base_url.strip():
                os.environ["GITHUB_API_URL"] = base_url.strip()
            if isinstance(token, str) and token.strip():
                os.environ["GITHUB_TOKEN"] = token.strip()
            if isinstance(mentions, str) and mentions.strip():
                os.environ["MENTIONS"] = mentions.strip()

            out = cmd_github_run(event_path=str(event_path) if isinstance(event_path, str) and event_path else None, print_prompt=print_prompt)
            sys.stdout.write(out + "\n")
            sys.stdout.flush()
            return 0
        parser.error("missing or unknown github subcommand")
        return 2

    parser.error(f"command not implemented: {ns.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
