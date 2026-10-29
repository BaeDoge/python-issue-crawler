"""Regression tests for repository-path validation in open-source drafts."""
import unittest

from verify.repository_paths import find_unverified_repository_paths


class RepositoryPathValidationTests(unittest.TestCase):
    def test_accepts_existing_files_and_parent_directories(self):
        tree = [
            "ch04/03_kv-cache/gpt_with_kv_cache.py",
            "appendix-E/01_main-chapter-code/gpt_download.py",
        ]
        text = (
            "See ch04/03_kv-cache/gpt_with_kv_cache.py and "
            "appendix-E/01_main-chapter-code/gpt_download.py."
        )
        self.assertEqual(find_unverified_repository_paths(text, tree), [])

    def test_detects_nonexistent_paths(self):
        tree = [
            "ch04/03_kv-cache/gpt_with_kv_cache.py",
            "appendix-E/01_main-chapter-code/gpt_download.py",
        ]
        text = (
            "See ch04/03_kv-cache/gpt_with_kv_cache.py, but the download path is "
            "appendix-D/gpt_download.py."
        )
        self.assertEqual(
            find_unverified_repository_paths(text, tree),
            ["appendix-D/gpt_download.py"],
        )

    def test_finds_paths_inside_github_blob_urls(self):
        tree = ["ch04/03_kv-cache/gpt_with_kv_cache.py"]
        text = (
            "Source: https://github.com/owner/repo/blob/main/ch04/03_kv-cache/"
            "gpt_with_kv_cache.py"
        )
        self.assertEqual(find_unverified_repository_paths(text, tree), [])


    def test_handles_non_chapter_repositories(self):
        tree = [
            "tensorflow/c/c_api.h",
            "tensorflow/c/eager/c_api.h",
            "tensorflow/core/public/session.h",
            "LICENSE",
        ]
        self.assertEqual(
            find_unverified_repository_paths(
                "See tensorflow/c/c_api.h and tensorflow/c/eager/c_api.h.",
                tree,
            ),
            [],
        )
        self.assertEqual(
            find_unverified_repository_paths(
                "See tensorflow/c/eager/not_a_real_header.h.",
                tree,
            ),
            ["tensorflow/c/eager/not_a_real_header.h"],
        )

    def test_ignores_external_urls(self):
        tree = ["tensorflow/c/c_api.h"]
        self.assertEqual(
            find_unverified_repository_paths(
                "Official URL: https://github.com/tensorflow/tensorflow/blob/master/tensorflow/c/c_api.h",
                tree,
            ),
            [],
        )

    def test_returns_no_findings_without_tree_data(self):
        self.assertEqual(find_unverified_repository_paths("ch04/not-real.py", None), [])


if __name__ == "__main__":
    unittest.main()
