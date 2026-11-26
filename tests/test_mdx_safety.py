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

    def test_preserves_supported_mdx_components_and_safe_html(self):
        source = (
            '<Callout type="info" title="참고">설명</Callout>\n'
            '<Compare><ComparePanel title="A">내용</ComparePanel></Compare>\n'
            "<p>일반 문단</p><br />\n"
        )
        actual, count = normalize_mdx_text(source)
        self.assertEqual(actual, source)
        self.assertEqual(count, 0)

    def test_escapes_unsupported_script_and_custom_tags(self):
        source = (
            "원본에 <script>const x = 1;</script>라는 문자열이 있습니다.\n"
            '사용자 XML <my-widget data-id="1">값</my-widget>도 설명합니다.'
        )
        actual, count = normalize_mdx_text(source)
        self.assertIn("&lt;script&gt;const x = 1;&lt;/script&gt;", actual)
        self.assertIn('&lt;my-widget data-id="1"&gt;값&lt;/my-widget&gt;', actual)
        self.assertEqual(count, 4)

    def test_is_idempotent(self):
        once, _ = normalize_mdx_text("조건은 n <= 10입니다.")
        twice, count = normalize_mdx_text(once)
        self.assertEqual(twice, once)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
