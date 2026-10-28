"""Regression tests for reviewer JSON parsing."""
import unittest

from verify.quality import extract_json


class ExtractJsonTests(unittest.TestCase):
    def test_plain_json_verdict(self):
        self.assertEqual(
            extract_json('{"passed": true, "issues": []}'),
            {"passed": True, "issues": []},
        )

    def test_think_tags_and_markdown_fence(self):
        fence = chr(96) * 3
        raw = '<think>discarded</think>\n' + fence + 'json\n{"passed": true, "issues": []}\n' + fence
        self.assertEqual(
            extract_json(raw),
            {"passed": True, "issues": []},
        )

    def test_unescaped_quotes_inside_issue_text(self):
        # Deliberately malformed JSON: the reviewer forgot to escape quotes in prose.
        raw = r'''{"passed": false, "issues": ["The configured value ">=3.10,<3.15" differs, and should be checked.", "The code refers to "GPTModel", but no file exists."]}'''
        result = extract_json(raw)
        self.assertIsNotNone(result)
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["issues"],
            [
                'The configured value ">=3.10,<3.15" differs, and should be checked.',
                'The code refers to "GPTModel", but no file exists.',
            ],
        )

    def test_unescaped_quotes_inside_issue_with_commas(self):
        raw = r'''{"passed": false, "issues": ["The phrase "foo", which appears in the note, is not backed by the source."]}'''
        self.assertEqual(
            extract_json(raw),
            {
                "passed": False,
                "issues": ['The phrase "foo", which appears in the note, is not backed by the source.'],
            },
        )

    def test_rejects_wrong_verdict_schema(self):
        self.assertIsNone(extract_json('{"passed": "false", "issues": []}'))
        self.assertIsNone(extract_json('{"passed": false, "issues": "not a list"}'))


if __name__ == "__main__":
    unittest.main()
