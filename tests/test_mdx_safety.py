import unittest

from verify.mdx import normalize_mdx_text


class MdxTextSafetyTests(unittest.TestCase):
    def test_escapes_less_than_and_less_than_or_equal_in_prose(self):
        source = "제약 조건은 n <= 50,000이고 값은 x < 100입니다."
        actual, count = normalize_mdx_text(source)
        self.assertEqual(
            actual,
            "제약 조건은 n &lt;= 50,000이고 값은 x &lt; 100입니다.",
        )
        self.assertEqual(count, 2)

    def test_escapes_adjacent_comparison_without_spaces(self):
        actual, count = normalize_mdx_text("조건은 n<k입니다.")
        self.assertEqual(actual, "조건은 n&lt;k입니다.")
        self.assertEqual(count, 1)

    def test_preserves_fenced_and_inline_code(self):
        source = (
            "문장에서는 n <= 10입니다.\n"
            "```python\n"
            "if n <= 10:\n"
            "    print(n < 5)\n"
            "```\n"
            "코드 `n <= 10`은 그대로 둡니다.\n"
        )
        actual, count = normalize_mdx_text(source)
        self.assertIn("문장에서는 n &lt;= 10입니다.", actual)
        self.assertIn("if n <= 10:", actual)
        self.assertIn("print(n < 5)", actual)
        self.assertIn("`n <= 10`", actual)
        self.assertEqual(count, 1)

    def test_preserves_jsx_tags_and_frontmatter(self):
        source = (
            "---\n"
            'title: "n <= 10"\n'
            "---\n"
            "컴포넌트 <Callout title=\"조건\" />를 사용합니다.\n"
        )
        actual, count = normalize_mdx_text(source)
        self.assertEqual(actual, source)
        self.assertEqual(count, 0)

    def test_is_idempotent(self):
        once, _ = normalize_mdx_text("조건은 n <= 10입니다.")
        twice, count = normalize_mdx_text(once)
        self.assertEqual(twice, once)
        self.assertEqual(count, 0)


    def test_converts_html_anchor_to_markdown_link(self):
        source = '참고 링크: <a href="https://example.org/docs" target="_blank">공식 문서</a>'
        actual, _ = normalize_mdx_text(source)
        self.assertEqual(actual, "참고 링크: [공식 문서](https://example.org/docs)")

    def test_removes_script_and_unknown_html_tags_from_prose(self):
        source = '원문에 <script src="https://example.org/x.js"></script>와 <unknown-tag>본문</unknown-tag>가 있습니다.'
        actual, _ = normalize_mdx_text(source)
        self.assertNotIn("<script", actual.lower())
        self.assertNotIn("</script>", actual.lower())
        self.assertNotIn("<unknown-tag", actual.lower())
        self.assertIn("본문", actual)

    def test_preserves_raw_html_examples_inside_fenced_code(self):
        fence = chr(96) * 3
        source = "HTML 예제입니다.\n" + fence + "html\n<script>console.log(1)</script>\n" + fence + "\n"
        actual, _ = normalize_mdx_text(source)
        self.assertIn("<script>console.log(1)</script>", actual)

    def test_converts_safe_html_image_to_markdown(self):
        source = '<img src="/images/example.png" alt="예시 화면">'
        actual, _ = normalize_mdx_text(source)
        self.assertEqual(actual, "![예시 화면](/images/example.png)")

    def test_preserves_supported_mdx_components(self):
        source = '<Callout type="info">본문</Callout>'
        actual, _ = normalize_mdx_text(source)
        self.assertEqual(actual, source)

if __name__ == "__main__":
    unittest.main()
