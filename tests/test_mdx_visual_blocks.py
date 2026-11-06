import unittest

from verify.mdx import normalize_mdx_text


class MdxVisualBlockTests(unittest.TestCase):
    def test_custom_visual_components_survive_mdx_normalization(self):
        source = """<Callout type="tip" title="설명">
본문의 비교식 a < b 는 텍스트로 남아야 합니다.
</Callout>

<StatGrid>
  <Stat value="1M+" label="분석 데이터" />
</StatGrid>
"""
        normalized, replacements = normalize_mdx_text(source)

        self.assertIn('<Callout type="tip" title="설명">', normalized)
        self.assertIn('<Stat value="1M+" label="분석 데이터" />', normalized)
        self.assertIn("a &lt; b", normalized)
        self.assertEqual(replacements, 1)

    def test_visual_components_inside_code_fences_are_not_modified(self):
        source = """```mdx
<Callout type="info">a < b</Callout>
```
"""
        normalized, replacements = normalize_mdx_text(source)

        self.assertEqual(normalized, source)
        self.assertEqual(replacements, 0)


if __name__ == "__main__":
    unittest.main()
