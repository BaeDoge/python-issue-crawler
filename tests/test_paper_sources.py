import unittest

from sources.papers import _abstract_from_index, _candidate, _extract_code_links, _arxiv_html_url


class PaperSourceTests(unittest.TestCase):
    def test_rebuilds_abstract_in_position_order(self):
        self.assertEqual(
            _abstract_from_index({"world": [1], "Hello": [0], "again": [2]}),
            "Hello world again",
        )

    def test_classifies_korean_affiliated_research(self):
        abstract = " ".join(f"word{i}" for i in range(40))
        work = {
            "title": "A research paper",
            "id": "https://openalex.org/W123",
            "abstract_inverted_index": {word: [i] for i, word in enumerate(abstract.split())},
            "authorships": [{"institutions": [{"country_code": "KR"}]}],
            "publication_date": "2026-01-01",
        }
        item = _candidate(work, "AI")
        self.assertIsNotNone(item)
        self.assertTrue(item["is_domestic"])
        self.assertEqual(item["type"], "domestic")

    def test_does_not_guess_code_repository(self):
        self.assertEqual(_extract_code_links("No official implementation is linked."), [])

    def test_extracts_explicit_github_url(self):
        html = '<p>Code: <a href="https://github.com/example/research-code">GitHub repository</a></p>'
        self.assertEqual(
            _extract_code_links(html),
            ["https://github.com/example/research-code"],
        )

    def test_maps_arxiv_abstract_to_html(self):
        self.assertEqual(
            _arxiv_html_url("https://arxiv.org/abs/2401.12345v2"),
            "https://arxiv.org/html/2401.12345v2",
        )


if __name__ == "__main__":
    unittest.main()
