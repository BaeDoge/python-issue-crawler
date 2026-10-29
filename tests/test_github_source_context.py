"""Tests for README sampling and GitHub candidate snapshot cleanup."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OMNIROUTE_API_KEY", "unit-test-only")

from sources import github_trending  # noqa: E402


class GithubSourceContextTests(unittest.TestCase):
    def test_large_catalog_readme_samples_sections_from_beginning_middle_and_end(self):
        sections = ["# Build your own X", "", "A collection of tutorials."]
        for index in range(1, 61):
            sections.extend([
                "",
                f"## Category {index:02d}",
                f"- [Tutorial {index:02d}](https://example.invalid/tutorial-{index:02d})",
                f"- Secondary entry for category {index:02d}",
            ])
        source = "\n".join(sections)

        excerpt = github_trending._catalog_readme_excerpt(source, max_chars=1800)

        self.assertLessEqual(len(excerpt), 1800)
        self.assertIn("Category 01", excerpt)
        self.assertIn("Category 60", excerpt)
        self.assertIn("대표 항목을 발췌", excerpt)

    def test_code_excerpt_includes_multiple_regions(self):
        source_lines = ["# source file"]
        for index in range(100):
            source_lines.extend([
                "",
                f"def function_{index}():",
                f"    return {index}",
            ])
        source = "\n".join(source_lines)

        excerpt = github_trending._code_excerpt("src/example.py", source, max_chars=1300)

        self.assertLessEqual(len(excerpt), 1300)
        self.assertIn("function_0", excerpt)
        self.assertIn("function_99", excerpt)

    def test_legacy_candidate_snapshots_leave_output_files_and_default_save_is_off(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output_dir = root / "output_files"
            log_dir = root / "logs"
            output_dir.mkdir()

            (output_dir / "github_opensource_candidates_20261027_100000.json").write_text("{}", encoding="utf-8")
            (output_dir / "github_opensource_candidates_20261028_100000.json").write_text("{}", encoding="utf-8")

            with (
                patch.object(github_trending, "OUTPUT_DIR", output_dir),
                patch.object(github_trending, "LOG_DIR", log_dir),
                patch.dict(os.environ, {
                    "GITHUB_SAVE_CANDIDATE_SNAPSHOTS": "false",
                    "GITHUB_CANDIDATE_SNAPSHOT_KEEP": "1",
                }),
            ):
                saved = github_trending._save_candidate_snapshot({"popular": [], "trending": []})

            self.assertIsNone(saved)
            self.assertEqual(list(output_dir.glob("github_opensource_candidates_*.json")), [])
            retained = list((log_dir / "github_candidates").glob("github_opensource_candidates_*.json"))
            self.assertLessEqual(len(retained), 1)


if __name__ == "__main__":
    unittest.main()
