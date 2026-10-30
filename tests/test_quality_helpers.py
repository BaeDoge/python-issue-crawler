import unittest

from verify.quality import detect_foreign_language_mixing, extract_json


class ForeignLanguageMixingTests(unittest.TestCase):
    def test_korean_technical_terms_are_allowed(self):
        text = (
            "PS5의 ELF 실행 파일을 Linux와 Windows 환경에서 분석합니다. "
            "NID와 SPIR-V, AMD Zen, Vulkan을 함께 설명합니다."
        )
        self.assertEqual(detect_foreign_language_mixing(text), [])

    def test_repository_paths_and_inline_code_are_ignored(self):
        text = (
            "실제 구현은 core/libs/prx/와 libSceKernel에서 확인합니다. "
            "자세한 내용은 https://example.com/日本語 에서 확인할 수 있습니다."
        )
        self.assertEqual(detect_foreign_language_mixing(text), [])

    def test_fenced_code_is_ignored_even_when_unclosed(self):
        fence = chr(96) * 3
        text = "한국어 설명입니다.\n" + fence + "text\nこれは日本語です"
        self.assertEqual(detect_foreign_language_mixing(text), [])

    def test_japanese_prose_is_detected(self):
        self.assertTrue(detect_foreign_language_mixing("これは日本語の文章です。"))

    def test_chinese_prose_is_detected(self):
        self.assertTrue(detect_foreign_language_mixing("这个项目是一个用于处理数据的工具。"))

    def test_short_han_terms_are_not_detected(self):
        self.assertEqual(detect_foreign_language_mixing("중국어 용어인 中国과 日本을 비교합니다."), [])


class ReviewJsonTests(unittest.TestCase):
    def test_json_after_reasoning_and_code_fence_is_parsed(self):
        fence = chr(96) * 3
        raw = '<think>internal reasoning</think>\n' + fence + 'json\n{"passed": true, "issues": []}\n' + fence
        self.assertEqual(extract_json(raw), {"passed": True, "issues": []})

    def test_unescaped_quotes_inside_issue_are_repaired(self):
        raw = '{"passed": false, "issues": ["파일 "README.md" 경로를 확인해야 합니다"]}'
        self.assertEqual(
            extract_json(raw),
            {"passed": False, "issues": ['파일 "README.md" 경로를 확인해야 합니다']},
        )

    def test_truncated_json_is_not_accepted(self):
        self.assertIsNone(extract_json('{"passed": false, "issues": ["잘린 응답'))


if __name__ == "__main__":
    unittest.main()
