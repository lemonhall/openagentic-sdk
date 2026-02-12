from __future__ import annotations


def parse_repl_command(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s.startswith("/"):
        return None
    s = s[1:].strip()
    if not s:
        return None
    parts = s.split(None, 1)
    name = parts[0].strip()
    arg = parts[1].strip() if len(parts) > 1 else ""
    # Only treat a small set as *REPL* commands. Other `/foo` inputs are passed
    # through to the agent runtime (OpenCode-style custom commands).
    if name not in {"exit", "quit", "help", "new", "interrupt", "debug", "skills", "skill", "cmd", "paste"}:
        return None
    return name, arg

