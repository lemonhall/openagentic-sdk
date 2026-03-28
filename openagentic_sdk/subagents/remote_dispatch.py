from __future__ import annotations

import subprocess


def resolve_git_revision(*, cwd: str) -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise RuntimeError("Remote task dispatch requires a git checkout with a committed HEAD")

    revision = (head.stdout or "").strip()
    if not revision:
        raise RuntimeError("Remote task dispatch could not resolve git revision")

    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if dirty.returncode != 0:
        raise RuntimeError("Remote task dispatch could not inspect git worktree state")
    if (dirty.stdout or "").strip():
        raise RuntimeError("Remote task dispatch requires a clean git worktree")

    return revision
