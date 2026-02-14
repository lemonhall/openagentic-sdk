from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Sequence

import importlib.util

from .tools.base import Tool


def _load_module_from_file(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"custom_tool_{path.stem}", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load custom tool module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[call-arg]
    return mod


def _default_global_opencode_config_dir() -> Path:
    return Path(os.environ.get("OPENCODE_CONFIG_DIR") or (Path.home() / ".config" / "opencode")).expanduser()


def discover_custom_tool_files(*, project_dir: str) -> list[Path]:
    base = Path(project_dir)
    global_root = _default_global_opencode_config_dir()

    # Precedence (low -> high): global < project < .opencode
    # Rationale: ToolRegistry is "last register wins", so we want higher-precedence
    # tools to be discovered later.
    roots: list[Path] = [global_root, base, base / ".opencode"]
    out: list[Path] = []
    for r in roots:
        # Precedence (low -> high): tool < tools
        for dirname in ("tool", "tools"):
            d = r / dirname
            if not d.exists() or not d.is_dir():
                continue
            out.extend([p for p in sorted(d.glob("*.py"), key=lambda p: p.name) if p.is_file()])
    return out


def load_custom_tools(*, project_dir: str) -> list[Tool]:
    tools: list[Tool] = []
    for p in discover_custom_tool_files(project_dir=project_dir):
        try:
            mod = _load_module_from_file(p)
        except Exception:
            continue
        items = getattr(mod, "TOOLS", None)
        if isinstance(items, list):
            for t in items:
                if isinstance(t, Tool):
                    tools.append(t)
        one = getattr(mod, "TOOL", None)
        if isinstance(one, Tool):
            tools.append(one)
    return tools
