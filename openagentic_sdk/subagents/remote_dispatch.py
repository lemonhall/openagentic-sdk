from __future__ import annotations

import subprocess
from pathlib import Path


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


def resolve_git_head_only(*, cwd: str) -> str:
    repo_root = Path(cwd).resolve()
    gitdir = _resolve_gitdir(repo_root)
    head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    if not head:
        raise RuntimeError("Remote worker could not resolve local git HEAD")

    if head.startswith("ref:"):
        ref_name = head.split(":", 1)[1].strip()
        revision = _read_ref(gitdir=gitdir, ref_name=ref_name)
    else:
        revision = head

    revision = revision.strip()
    if len(revision) < 7:
        raise RuntimeError("Remote worker resolved an invalid git revision")
    return revision


def _resolve_gitdir(repo_root: Path) -> Path:
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        raw = dot_git.read_text(encoding="utf-8").strip()
        if not raw.startswith("gitdir:"):
            raise RuntimeError("Remote worker could not parse .git file")
        rel = raw.split(":", 1)[1].strip()
        return (repo_root / rel).resolve()
    raise RuntimeError("Remote worker requires a git checkout")


def _read_ref(*, gitdir: Path, ref_name: str) -> str:
    direct = (gitdir / ref_name).resolve()
    if direct.exists():
        return direct.read_text(encoding="utf-8").strip()

    common_dir = _resolve_common_dir(gitdir)
    common_ref = (common_dir / ref_name).resolve()
    if common_ref.exists():
        return common_ref.read_text(encoding="utf-8").strip()

    packed_candidates = [gitdir / "packed-refs"]
    if common_dir != gitdir:
        packed_candidates.append(common_dir / "packed-refs")

    for packed in packed_candidates:
        if not packed.exists():
            continue
        for raw in packed.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            sha, _, name = line.partition(" ")
            if name == ref_name:
                return sha.strip()

    raise RuntimeError(f"Remote worker could not resolve git ref '{ref_name}'")


def _resolve_common_dir(gitdir: Path) -> Path:
    common = gitdir / "commondir"
    if not common.exists():
        return gitdir
    raw = common.read_text(encoding="utf-8").strip()
    if not raw:
        return gitdir
    return (gitdir / raw).resolve()
