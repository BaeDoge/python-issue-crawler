import unittest

from topics.note_format import _unwrap_outer_fence, parse_note_text
from verify.code_blocks import (
    iter_fenced_code_blocks,
    mask_fenced_code_blocks,
    normalize_fenced_code_blocks,
)


class MarkdownFenceTests(unittest.TestCase):
    def test_parses_four_tilde_python_fence(self):
        source = "before\n~~~~python\nvalue = 1\n~~~~\nafter\n"

        blocks = list(iter_fenced_code_blocks(source))

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].language, "python")
        self.assertEqual(blocks[0].marker, "~~~~")
        self.assertTrue(blocks[0].complete)
        self.assertEqual(blocks[0].body, "value = 1\n")

    def test_closing_fence_may_be_longer_than_opening_fence(self):
        source = "~~~python\nvalue = 1\n~~~~~\n"
        blocks = list(iter_fenced_code_blocks(source))

        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0].complete)
        self.assertEqual(blocks[0].body, "value = 1\n")

    def test_normalizes_tilde_fences_to_backticks(self):
        fence = chr(96) * 3
        source = "설명\n\n~~~~python\nvalue = 1\n~~~~\n\n마무리"
        normalized = normalize_fenced_code_blocks(source)

        self.assertIn(fence + "python\nvalue = 1\n" + fence, normalized)
        self.assertNotIn("~~~~", normalized)
        self.assertEqual(normalize_fenced_code_blocks(normalized), normalized)

    def test_normalizer_keeps_nested_backtick_fences_inside_outer_block(self):
        fence = chr(96) * 3
        source = "~~~~markdown\n" + fence + "python\nprint(1)\n" + fence + "\n~~~~"
        normalized = normalize_fenced_code_blocks(source)
        blocks = list(iter_fenced_code_blocks(normalized))

        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0].complete)
        self.assertGreaterEqual(len(blocks[0].marker), 4)
        self.assertIn(fence + "python", blocks[0].body)

    def test_masks_code_without_changing_line_count(self):
        source = "한글 설명\n~~~~python\nこれはコード\n~~~~\n다음 설명"
        masked = mask_fenced_code_blocks(source)

        self.assertEqual(masked.count("\n"), source.count("\n"))
        self.assertIn("한글 설명", masked)
        self.assertIn("다음 설명", masked)
        self.assertNotIn("これはコード", masked)

    def test_unwraps_outer_tilde_markdown_fence(self):
        source = "~~~~markdown\n제목: sample\n## 풀이\ntext\n~~~~"
        unwrapped = _unwrap_outer_fence(source)

        self.assertIn("제목: sample", unwrapped)
        self.assertNotIn("~~~~markdown", unwrapped)

    def test_unclosed_fence_is_reported_as_incomplete(self):
        blocks = list(iter_fenced_code_blocks("본문\n~~~python\nprint(1)\n"))

        self.assertEqual(len(blocks), 1)
        self.assertFalse(blocks[0].complete)

    def test_note_parser_does_not_treat_heading_inside_tilde_fence_as_section(self):
        raw = (
            "제목: [코딩테스트] 예시\n"
            "요약: 코드 펜스 안의 제목을 섹션으로 오인하지 않는지 확인합니다.\n\n"
            "## 풀이\n"
            "~~~~python\n"
            "def example():\n"
            "    # 다음 줄은 코드의 일부입니다.\n"
            "    ## 가짜 섹션\n"
            "    return 1\n"
            "~~~~\n"
        )
        parsed = parse_note_text(raw, ["풀이"])

        self.assertIsNotNone(parsed)
        self.assertEqual(list(parsed["sections"]), ["풀이"])
        self.assertIn("## 가짜 섹션", parsed["sections"]["풀이"])


if __name__ == "__main__":
    unittest.main()
