from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .remote_dispatch import resolve_git_head_only


@dataclass(frozen=True, slots=True)
class GitSyncResult:
    status: str
    target_revision: str | None = None
    reason: str | None = None
    updated_mirrors: tuple[str, ...] = ()
    rolled_back_mirrors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.target_revision:
            payload["target_revision"] = self.target_revision
        if self.reason:
            payload["reason"] = self.reason
        if self.updated_mirrors:
            payload["updated_mirrors"] = list(self.updated_mirrors)
        if self.rolled_back_mirrors:
            payload["rolled_back_mirrors"] = list(self.rolled_back_mirrors)
        return payload


class CommittedGitSynchronizer:
    def __init__(self, *, authoritative_cwd: str, mirror_cwds: Sequence[str] = ()) -> None:
        self._authoritative = Path(authoritative_cwd).resolve()
        self._mirrors = tuple(Path(item).resolve() for item in mirror_cwds)
        self._baseline_manifest = (
            _capture_worktree_manifest(self._authoritative)
            if shutil.which("git") is None and not self._mirrors
            else None
        )

    def sync(self) -> GitSyncResult:
        target_revision = self._resolve_authoritative_revision()
        if target_revision is None:
            return GitSyncResult(status="blocked", reason="dirty-worktree")

        if not self._mirrors:
            return GitSyncResult(status="ok", target_revision=target_revision)

        previous_heads: dict[Path, str] = {}
        updated: list[Path] = []
        try:
            for mirror in self._mirrors:
                if mirror == self._authoritative:
                    continue
                previous_heads[mirror] = self._git_head(mirror)
                self._sync_mirror(mirror, target_revision)
                updated.append(mirror)
        except Exception as e:  # noqa: BLE001
            rolled_back: list[str] = []
            for mirror in reversed(updated):
                previous = previous_heads.get(mirror)
                if not previous:
                    continue
                try:
                    self._git(mirror, "checkout", "--force", previous)
                    rolled_back.append(str(mirror))
                except Exception:
                    continue
            return GitSyncResult(
                status="error",
                target_revision=target_revision,
                reason=str(e),
                updated_mirrors=tuple(str(item) for item in updated),
                rolled_back_mirrors=tuple(rolled_back),
            )

        return GitSyncResult(
            status="ok",
            target_revision=target_revision,
            updated_mirrors=tuple(str(item) for item in updated),
        )

    def _resolve_authoritative_revision(self) -> str | None:
        if shutil.which("git") is None:
            revision = resolve_git_head_only(cwd=str(self._authoritative))
            if self._mirrors:
                raise RuntimeError("git executable is required to sync mirror worktrees")
            baseline = self._baseline_manifest or {}
            return None if _capture_worktree_manifest(self._authoritative) != baseline else revision

        revision = self._git(self._authoritative, "rev-parse", "HEAD").stdout.strip()
        if not revision:
            raise RuntimeError("authoritative repository does not have a committed HEAD")
        dirty = self._git(self._authoritative, "status", "--porcelain")
        if dirty.stdout.strip():
            return None
        return revision

    def _sync_mirror(self, mirror: Path, revision: str) -> None:
        if not mirror.exists():
            raise RuntimeError(f"mirror path does not exist: {mirror}")
        self._git(mirror, "fetch", "--force", str(self._authoritative), revision)
        self._git(mirror, "checkout", "--force", revision)

    def _git_head(self, repo: Path) -> str:
        return self._git(repo, "rev-parse", "HEAD").stdout.strip()

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )


def _capture_worktree_manifest(repo_root: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for current_path in sorted(repo_root.rglob("*")):
        if current_path.is_dir():
            if current_path.name in {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}:
                continue
            continue
        if ".git" in current_path.parts or "__pycache__" in current_path.parts:
            continue
        if current_path.suffix in {".pyc", ".pyo"}:
            continue
        rel_path = current_path.relative_to(repo_root).as_posix()
        data = current_path.read_bytes()
        manifest[rel_path] = hashlib.sha1(data).hexdigest()
    return manifest
