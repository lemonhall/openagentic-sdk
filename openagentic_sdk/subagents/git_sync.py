from __future__ import annotations

import os
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
            return None if _worktree_is_dirty_without_git(self._authoritative) else revision

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


def _worktree_is_dirty_without_git(repo_root: Path) -> bool:
    tracked = _tracked_index_entries(repo_root)
    tracked_paths = set(tracked.keys())

    for rel_path, stat_info in tracked.items():
        file_path = repo_root / rel_path
        if not file_path.exists():
            return True
        current = file_path.stat()
        current_mtime_ns = int(getattr(current, "st_mtime_ns", int(current.st_mtime * 1_000_000_000)))
        expected_mtime_ns = int(stat_info["mtime_ns"])
        if int(current.st_size) != int(stat_info["size"]):
            return True
        if current_mtime_ns != expected_mtime_ns:
            return True

    for current_path in repo_root.rglob("*"):
        if current_path.is_dir():
            if current_path.name == ".git":
                continue
            continue
        if ".git" in current_path.parts:
            continue
        rel_path = current_path.relative_to(repo_root).as_posix()
        if rel_path not in tracked_paths:
            return True
    return False


def _tracked_index_entries(repo_root: Path) -> dict[str, dict[str, int]]:
    gitdir = _resolve_gitdir(repo_root)
    index_path = gitdir / "index"
    if not index_path.exists():
        return {}

    data = index_path.read_bytes()
    if len(data) < 12 or data[:4] != b"DIRC":
        return {}
    entry_count = int.from_bytes(data[8:12], "big")
    offset = 12
    entries: dict[str, dict[str, int]] = {}
    for _ in range(entry_count):
        entry_start = offset
        if entry_start + 62 > len(data):
            break
        mtime_seconds = int.from_bytes(data[16:20], "big")
        mtime_nanoseconds = int.from_bytes(data[20:24], "big")
        size = int.from_bytes(data[36:40], "big")
        flags = int.from_bytes(data[60:62], "big")
        path_start = entry_start + 62
        if flags & 0x4000:
            path_start += 2
        path_end = data.find(b"\x00", path_start)
        if path_end == -1:
            break
        rel_path = data[path_start:path_end].decode("utf-8", errors="surrogateescape")
        entries[rel_path] = {
            "size": size,
            "mtime_ns": mtime_seconds * 1_000_000_000 + mtime_nanoseconds,
        }
        entry_length = path_end - entry_start + 1
        padding = (8 - (entry_length % 8)) % 8
        offset = path_end + 1 + padding
    return entries


def _resolve_gitdir(repo_root: Path) -> Path:
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        raw = dot_git.read_text(encoding="utf-8").strip()
        if not raw.startswith("gitdir:"):
            raise RuntimeError("could not parse .git file")
        rel = raw.split(":", 1)[1].strip()
        candidate = (repo_root / rel).resolve()
        if os.path.isabs(rel):
            candidate = Path(rel).resolve()
        return candidate
    raise RuntimeError("repository requires a .git directory or file")
