import unittest

from output.note import _dedupe_sources, _source_line, _source_line_en


class PaperSourceLinkTests(unittest.TestCase):
    def test_deduplicates_doi_aliases_and_keeps_the_original_paper_link(self):
        sources = [
            {
                "platform": "OpenAlex / 논문 원문",
                "title": "Example paper",
                "url": "https://doi.org/10.1234/Example.DOI",
            },
            {
                "platform": "Open Access PDF",
                "title": "논문 PDF",
                "url": "https://dx.doi.org/10.1234/example.doi",
            },
            {
                "platform": "논문 HTML 원문",
                "title": "Example paper",
                "url": "https://www.doi.org/10.1234/example.doi/",
            },
            {
                "platform": "GitHub 저장소",
                "title": "example/research-code",
                "url": "https://github.com/example/research-code",
            },
        ]

        unique = _dedupe_sources(sources)

        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]["platform"], "OpenAlex / 논문 원문")
        self.assertEqual(unique[1]["platform"], "GitHub 저장소")

    def test_deduplicates_trailing_slashes_and_ignores_empty_urls(self):
        sources = [
            {"platform": "논문", "title": "Paper", "url": "https://journal.example/paper/123"},
            {"platform": "PDF", "title": "PDF", "url": "https://journal.example/paper/123/"},
            {"platform": "출처 누락", "title": "Unknown", "url": ""},
        ]

        unique = _dedupe_sources(sources)

        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["platform"], "논문")

    def test_source_markdown_escapes_html_like_labels_and_url_brackets(self):
        source = {
            "platform": "Reference <script>",
            "title": "Example <script>alert(1)</script> [paper]",
            "url": "https://example.com/paper/<script>?q=1",
            "author": "A. Author <iframe>",
        }

        rendered = _source_line(source)

        self.assertIn("Reference &lt;script&gt;", rendered)
        self.assertIn("Example &lt;script&gt;alert(1)&lt;/script&gt; \\[paper\\]", rendered)
        self.assertIn("https://example.com/paper/%3Cscript%3E?q=1", rendered)
        self.assertIn("A. Author &lt;iframe&gt;", rendered)

    def test_english_source_markdown_uses_the_same_safe_url_rules(self):
        source = {
            "platform": "Source",
            "title": "A title <script>",
            "url": "https://example.com/path/<script>",
            "author": "A. Author",
        }

        rendered = _source_line_en(source)

        self.assertIn("A title &lt;script&gt;", rendered)
        self.assertIn("https://example.com/path/%3Cscript%3E", rendered)


if __name__ == "__main__":
    unittest.main()
