import unittest

from output.note import _dedupe_sources


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


if __name__ == "__main__":
    unittest.main()
