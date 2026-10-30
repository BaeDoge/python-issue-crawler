"""Tests for actionable Git publisher failure diagnostics."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OMNIROUTE_API_KEY", "unit-test-only")

from publish.git_publish import PublishError, _run_git  # noqa: E402


class RunGitDiagnosticsTests(unittest.TestCase):
    @patch("publish.git_publish.subprocess.run")
    def test_nonzero_exit_preserves_stage_command_and_both_streams(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["git", "push", "origin", "main"],
            returncode=1,
            stdout="remote: rejected\n",
            stderr="fatal: authentication failed\n",
        )

        with self.assertRaises(PublishError) as raised:
            _run_git(Path("."), "push", "origin", "main", stage="Git push")

        error = raised.exception
        self.assertEqual(error.stage, "Git push")
        self.assertEqual(error.command, ["git", "push", "origin", "main"])
        self.assertEqual(error.returncode, 1)
        self.assertIn("authentication failed", error.stderr)
        self.assertIn("remote: rejected", error.stdout)
        self.assertIn("종료 코드: 1", str(error))

    @patch("publish.git_publish.subprocess.run")
    def test_timeout_is_reported_with_stage_and_command(self, run):
        run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "fetch", "origin", "main"],
            timeout=90,
            stderr="network timeout",
        )

        with self.assertRaises(PublishError) as raised:
            _run_git(Path("."), "fetch", "origin", "main", stage="원격 저장소 fetch")

        self.assertEqual(raised.exception.stage, "원격 저장소 fetch")
        self.assertEqual(
            raised.exception.command,
            ["git", "fetch", "origin", "main"],
        )
        self.assertIn("90초", str(raised.exception))

    @patch("publish.git_publish.subprocess.run")
    def test_missing_git_executable_is_reported(self, run):
        run.side_effect = FileNotFoundError("git executable not found")

        with self.assertRaises(PublishError) as raised:
            _run_git(Path("."), "status", stage="작업 트리 상태 확인")

        self.assertEqual(raised.exception.stage, "작업 트리 상태 확인")
        self.assertIsNone(raised.exception.returncode)
        self.assertIn("FileNotFoundError", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
