import os
import unittest
from unittest.mock import patch

os.environ.setdefault("OMNIROUTE_API_KEY", "unit-test-only")

from topics import algorithm


class AlgorithmReviewerEvidenceTests(unittest.TestCase):
    def test_original_leetcode_problem_is_passed_to_reviewer_context(self):
        source_text = (
            "[LeetCode: Two Sum] (난이도: Easy)\n"
            "원문: https://leetcode.com/problems/two-sum/\n"
            "지문: 정수 배열과 target이 주어집니다."
        )
        candidate = {
            "title": "LeetCode 1 - Two Sum",
            "title_slug": "two-sum",
            "link": "https://leetcode.com/problems/two-sum/",
            "tags": ["Array", "Hash Table"],
        }

        with patch.object(algorithm, "problem_context_text", return_value=source_text):
            context = algorithm._build_context(candidate)

        self.assertIn("review_context", context)
        self.assertIn("LeetCode 원문 문제 지문", context["review_context"])
        self.assertIn("정수 배열과 target", context["review_context"])
        self.assertIn("Two Sum", context["review_context"])
        self.assertIn("Hash Table", context["context_text"])

    def test_missing_source_context_is_not_fabricated(self):
        candidate = {
            "title": "LeetCode - unavailable",
            "title_slug": "missing-problem",
            "link": "https://leetcode.com/problems/missing-problem/",
            "tags": [],
        }

        with patch.object(algorithm, "problem_context_text", return_value=""):
            context = algorithm._build_context(candidate)

        self.assertEqual(context["context_text"], "")
        self.assertIsNone(context["source_url"])
        self.assertNotIn("review_context", context)


if __name__ == "__main__":
    unittest.main()
