from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestRemoteGitSyncPolicy(unittest.TestCase):
    def test_sync_updates_clean_worker_mirrors_to_latest_committed_revision(self) -> None:
        from openagentic_sdk.subagents.git_sync import CommittedGitSynchronizer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            authoritative = sandbox / "authoritative"
            mirror_a = sandbox / "mirror-a"
            mirror_b = sandbox / "mirror-b"
            self._init_repo(authoritative)
            self._clone_repo(authoritative, mirror_a)
            self._clone_repo(authoritative, mirror_b)

            (authoritative / "README.md").write_text("v2\n", encoding="utf-8")
            self._git(authoritative, "add", "README.md")
            self._git(authoritative, "commit", "-m", "v2")
            target_revision = self._head(authoritative)

            result = CommittedGitSynchronizer(
                authoritative_cwd=str(authoritative),
                mirror_cwds=(str(mirror_a), str(mirror_b)),
            ).sync()

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.target_revision, target_revision)
            self.assertEqual(self._head(mirror_a), target_revision)
            self.assertEqual(self._head(mirror_b), target_revision)

    def test_sync_blocks_when_authoritative_worktree_is_dirty(self) -> None:
        from openagentic_sdk.subagents.git_sync import CommittedGitSynchronizer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            authoritative = sandbox / "authoritative"
            mirror_a = sandbox / "mirror-a"
            self._init_repo(authoritative)
            self._clone_repo(authoritative, mirror_a)
            old_revision = self._head(mirror_a)

            (authoritative / "README.md").write_text("dirty\n", encoding="utf-8")

            result = CommittedGitSynchronizer(
                authoritative_cwd=str(authoritative),
                mirror_cwds=(str(mirror_a),),
            ).sync()

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.reason, "dirty-worktree")
            self.assertEqual(self._head(mirror_a), old_revision)

    def test_sync_rolls_back_updated_mirrors_when_later_target_fails(self) -> None:
        from openagentic_sdk.subagents.git_sync import CommittedGitSynchronizer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            authoritative = sandbox / "authoritative"
            mirror_a = sandbox / "mirror-a"
            missing_mirror = sandbox / "missing-mirror"
            self._init_repo(authoritative)
            self._clone_repo(authoritative, mirror_a)
            original_revision = self._head(mirror_a)

            (authoritative / "README.md").write_text("v2\n", encoding="utf-8")
            self._git(authoritative, "add", "README.md")
            self._git(authoritative, "commit", "-m", "v2")

            result = CommittedGitSynchronizer(
                authoritative_cwd=str(authoritative),
                mirror_cwds=(str(mirror_a), str(missing_mirror)),
            ).sync()

            self.assertEqual(result.status, "error")
            self.assertTrue(result.reason)
            self.assertEqual(self._head(mirror_a), original_revision)

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

    def _init_repo(self, root: Path) -> None:
        self._git(root.parent if root.exists() else root.parent, "init", str(root))
        self._git(root, "config", "user.email", "test@example.com")
        self._git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("v1\n", encoding="utf-8")
        self._git(root, "add", "README.md")
        self._git(root, "commit", "-m", "init")

    def _clone_repo(self, src: Path, dest: Path) -> None:
        subprocess.run(["git", "clone", str(src), str(dest)], check=True, capture_output=True, text=True)
        self._git(dest, "config", "user.email", "test@example.com")
        self._git(dest, "config", "user.name", "Test User")

    def _head(self, root: Path) -> str:
        return self._git(root, "rev-parse", "HEAD").stdout.strip()


if __name__ == "__main__":
    unittest.main()
