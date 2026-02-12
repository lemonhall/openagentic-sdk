from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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


@contextmanager
def temp_project_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="oa-win-cli-e2e-") as td:
        p = Path(td)
        (p / "project").mkdir(parents=True, exist_ok=True)
        (p / "home").mkdir(parents=True, exist_ok=True)
        yield p

