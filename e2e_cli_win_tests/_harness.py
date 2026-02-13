from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "RIGHTCODE_API_KEY": ("OPENAI_API_KEY",),
    "RIGHTCODE_BASE_URL": ("OPENAI_BASE_URL",),
}


def _maybe_load_dotenv() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / ".env"
    if not p.exists() or not p.is_file():
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        if not key:
            continue
        val = v.strip()
        if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
            val = val[1:-1]
        if key and key not in os.environ and val:
            os.environ[key] = val


_maybe_load_dotenv()


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v
    for alt in _ENV_ALIASES.get(name, ()):
        v2 = os.environ.get(alt)
        if v2:
            os.environ[name] = v2
            return v2
    raise RuntimeError(f"Missing required env var: {name}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_conpty_expect_on_syspath() -> None:
    root = repo_root()
    src = root / "packages" / "conpty-expect" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


@contextmanager
def temp_project_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="oa-win-cli-e2e-") as td:
        p = Path(td)
        (p / "project").mkdir(parents=True, exist_ok=True)
        (p / "home").mkdir(parents=True, exist_ok=True)
        yield p


def build_base_env(*, root: Path, home_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["OPENAGENTIC_SDK_HOME"] = str(home_dir)
    env["OPENCODE_TEST_HOME"] = str(home_dir)
    env["XDG_CONFIG_HOME"] = str(home_dir)
    env["OA_PERMISSION_MODE"] = "bypass"
    env["OA_CLI_AUTOAPPROVE_PROMPT"] = "0"
    env["OA_SHOW_THINKING"] = "0"
    env["OA_TRACE"] = "1"
    env["OA_BRACKETED_PASTE"] = "0"
    env["NO_COLOR"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("RIGHTCODE_TIMEOUT_S", "120")
    env.setdefault("RIGHTCODE_MAX_RETRIES", "6")
    env.setdefault("RIGHTCODE_RETRY_BACKOFF_S", "0.75")
    return env


def session_ids(session_root: Path) -> list[str]:
    d = Path(session_root) / "sessions"
    if not d.exists():
        return []
    out: list[str] = []
    for p in d.iterdir():
        if p.is_dir():
            out.append(p.name)
    return sorted(out)


def wait_for_single_session_id(session_root: Path, *, timeout_s: float = 5.0) -> str:
    deadline = time.time() + max(0.1, float(timeout_s))
    last: list[str] = []
    while time.time() < deadline:
        last = session_ids(session_root)
        if len(last) == 1:
            return last[0]
        time.sleep(0.05)
    raise AssertionError(f"expected exactly 1 session under {session_root!s}, got: {last!r}")


def read_events_jsonl(session_root: Path, session_id: str) -> list[dict[str, Any]]:
    p = Path(session_root) / "sessions" / str(session_id) / "events.jsonl"
    if not p.exists():
        raise FileNotFoundError(str(p))
    out: list[dict[str, Any]] = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def count_event_type(events: list[dict[str, Any]], typ: str) -> int:
    return sum(1 for e in events if e.get("type") == typ)

