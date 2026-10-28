"""Integration-style tests for publisher Git branch synchronization."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Importing the publisher loads shared LLM config. No LLM calls are made by these tests.
os.environ.setdefault("OMNIROUTE_API_KEY", "unit-test-only")

from publish.git_publish import PublishError, _sync_branch  # noqa: E402


def git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


@unittest.skipUnless(shutil.which("git"), "Git executable is required")
class SyncBranchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin.git"
        seed = self.root / "seed"
        seed.mkdir()

        git(seed, "init")
        git(seed, "symbolic-ref", "HEAD", "refs/heads/main")
        git(seed, "config", "user.name", "Publisher test")
        git(seed, "config", "user.email", "publisher-test@example.invalid")
        (seed / "README.md").write_text("base\n", encoding="utf-8")
        git(seed, "add", "README.md")
        git(seed, "commit", "-m", "base commit")

        git(self.root, "init", "--bare", str(self.origin))
        git(seed, "remote", "add", "origin", str(self.origin))
        git(seed, "push", "-u", "origin", "main")
        subprocess.run(
            ["git", "--git-dir", str(self.origin), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.local = self.root / "local"
        git(self.root, "clone", "--branch", "main", str(self.origin), str(self.local))
        git(self.local, "config", "user.name", "Publisher test")
        git(self.local, "config", "user.email", "publisher-test@example.invalid")

        self.remote_work = self.root / "remote-work"
        git(self.root, "clone", "--branch", "main", str(self.origin), str(self.remote_work))
        git(self.remote_work, "config", "user.name", "Publisher test")
        git(self.remote_work, "config", "user.email", "publisher-test@example.invalid")

    def tearDown(self):
        self.temp.cleanup()

    def _commit(self, repo: Path, path: str, content: str, message: str):
        (repo / path).write_text(content, encoding="utf-8")
        git(repo, "add", path)
        git(repo, "commit", "-m", message)

    def _push_remote_commit(self, path: str, content: str, message: str):
        self._commit(self.remote_work, path, content, message)
        git(self.remote_work, "push", "origin", "main")

    def test_fast_forwards_when_only_remote_is_ahead(self):
        self._push_remote_commit("remote.txt", "remote\n", "remote update")
        git(self.local, "fetch", "origin", "main")

        _sync_branch(self.local, "main")

        self.assertEqual(
            git(self.local, "rev-parse", "HEAD").stdout.strip(),
            git(self.local, "rev-parse", "origin/main").stdout.strip(),
        )
        self.assertTrue((self.local / "remote.txt").is_file())

    def test_rebases_local_commit_when_branches_diverge(self):
        self._commit(self.local, "local.txt", "local\n", "local-only update")
        local_commit_before = git(self.local, "rev-parse", "HEAD").stdout.strip()
        self._push_remote_commit("remote.txt", "remote\n", "remote-only update")
        git(self.local, "fetch", "origin", "main")

        _sync_branch(self.local, "main")

        self.assertNotEqual(git(self.local, "rev-parse", "HEAD").stdout.strip(), local_commit_before)
        self.assertTrue((self.local / "local.txt").is_file())
        self.assertTrue((self.local / "remote.txt").is_file())
        self.assertEqual(git(self.local, "status", "--porcelain").stdout.strip(), "")
        counts = git(self.local, "rev-list", "--left-right", "--count", "HEAD...origin/main").stdout.split()
        self.assertEqual(counts, ["1", "0"])

    def test_aborts_rebase_and_preserves_local_commit_on_conflict(self):
        self._commit(self.local, "README.md", "local edit\n", "local edit")
        local_commit_before = git(self.local, "rev-parse", "HEAD").stdout.strip()
        self._commit(self.remote_work, "README.md", "remote edit\n", "remote edit")
        git(self.remote_work, "push", "origin", "main")
        git(self.local, "fetch", "origin", "main")

        with self.assertRaises(PublishError) as raised:
            _sync_branch(self.local, "main")

        self.assertIn("자동 rebase에 충돌", str(raised.exception))
        self.assertEqual(git(self.local, "rev-parse", "HEAD").stdout.strip(), local_commit_before)
        self.assertEqual(git(self.local, "status", "--porcelain").stdout.strip(), "")
        self.assertFalse((self.local / ".git" / "rebase-merge").exists())
        self.assertFalse((self.local / ".git" / "rebase-apply").exists())


if __name__ == "__main__":
    unittest.main()
