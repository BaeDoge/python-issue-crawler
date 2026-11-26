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
            "~~~python\n"
            "if n <= 10:\n"
            "    print(n < 5)\n"
            "~~~\n"
            "코드 `n <= 10`은 그대로 둡니다.\n"
        )
        actual, count = normalize_mdx_text(source)
        self.assertIn("문장에서는 n &lt;= 10입니다.", actual)
        self.assertIn("if n <= 10:", actual)
        self.assertIn("print(n < 5)", actual)
        self.assertIn("`n <= 10`", actual)
        self.assertEqual(count, 1)

    def test_preserves_project_components_and_safe_html(self):
        source = (
            "컴포넌트 <Callout title=\"조건\" />를 사용합니다.\n"
            "줄바꿈<br />과 <strong>강조</strong>도 유지합니다."
        )
        actual, count = normalize_mdx_text(source)
        self.assertEqual(actual, source)
        self.assertEqual(count, 0)

    def test_escapes_script_and_unknown_html_like_tags(self):
        source = "원문 링크에 <script>alert(1)</script>와 <widget>가 포함되어 있습니다."
        actual, count = normalize_mdx_text(source)
        self.assertEqual(
            actual,
            "원문 링크에 &lt;script&gt;alert(1)&lt;/script&gt;와 &lt;widget&gt;가 포함되어 있습니다.",
        )
        self.assertEqual(count, 3)

    def test_percent_encodes_angle_brackets_inside_markdown_link_destination(self):
        source = "[원문](https://example.com/path/<script>?x=1)"
        actual, count = normalize_mdx_text(source)
        self.assertEqual(
            actual,
            "[원문](https://example.com/path/%3Cscript%3E?x=1)",
        )
        self.assertEqual(count, 0)

    def test_escapes_tag_like_text_in_markdown_link_label(self):
        source = "[<script>](https://example.com/)"
        actual, count = normalize_mdx_text(source)
        self.assertEqual(actual, "[&lt;script&gt;](https://example.com/)")
        self.assertEqual(count, 1)

    def test_preserves_frontmatter(self):
        source = (
            "---\n"
            'title: "n <= 10 <script>"\n'
            "---\n"
            "본문입니다.\n"
        )
        actual, count = normalize_mdx_text(source)
        self.assertEqual(actual, source)
        self.assertEqual(count, 0)

    def test_is_idempotent(self):
        once, _ = normalize_mdx_text("조건은 n <= 10입니다. <script>literal</script>")
        twice, count = normalize_mdx_text(once)
        self.assertEqual(twice, once)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
