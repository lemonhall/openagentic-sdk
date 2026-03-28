from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


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
