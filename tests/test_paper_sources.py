import base64
import unittest

from unittest.mock import patch

from sources.papers import (
    _abstract_from_index, _candidate, _extract_code_links, _arxiv_html_url,
    _is_developer_focused, _verify_public_github_repositories, _base_interest_score,
    _repository_interest_score, discover_candidates,
)


class PaperSourceTests(unittest.TestCase):
    def test_rebuilds_abstract_in_position_order(self):
        self.assertEqual(
            _abstract_from_index({"world": [1], "Hello": [0], "again": [2]}),
            "Hello world again",
        )

    def test_classifies_korean_affiliated_research(self):
        abstract = " ".join(f"word{i}" for i in range(40))
        work = {
            "title": "A database system research paper",
            "id": "https://openalex.org/W123",
            "abstract_inverted_index": {word: [i] for i, word in enumerate(abstract.split())},
            "authorships": [{"institutions": [{"country_code": "KR"}]}],
            "publication_date": "2026-01-01",
        }
        item = _candidate(work, "AI")
        self.assertIsNotNone(item)
        self.assertTrue(item["is_domestic"])
        self.assertEqual(item["type"], "domestic")

    def test_filters_papers_outside_development_scope(self):
        self.assertFalse(
            _is_developer_focused(
                "Digital diplomacy and legal immunity",
                "This paper discusses international law and diplomatic policy.",
            )
        )
        self.assertFalse(
            _is_developer_focused(
                "Generative AI in Korean language education",
                "This study focuses on teaching strategy and language learning.",
            )
        )
        self.assertFalse(
            _is_developer_focused(
                "Social network theory and civic participation",
                "We study network effects in communities and public institutions.",
            )
        )

    def test_keeps_computing_research(self):
        self.assertTrue(
            _is_developer_focused(
                "Reducing interference in large language model knowledge editing",
                "We study model editing algorithms for large language models.",
            )
        )
        self.assertTrue(
            _is_developer_focused(
                "분산 데이터베이스의 쿼리 최적화",
                "대규모 분산 시스템에서 데이터베이스 처리 성능을 개선합니다.",
            )
        )
        self.assertTrue(
            _is_developer_focused(
                "AI agent tool-use benchmark",
                "We evaluate agentic systems and function calling for software tasks.",
            )
        )

    def test_uses_recent_citation_counts_for_interest(self):
        recent = {
            "publication_date": "2026-01-01",
            "year": 2026,
            "recent_citations_2y": 24,
            "cited_by_count": 30,
            "fwci": 2.0,
            "citation_percentile": 0.8,
        }
        quiet = {
            "publication_date": "2026-01-01",
            "year": 2026,
            "recent_citations_2y": 0,
            "cited_by_count": 0,
            "fwci": 0.0,
            "citation_percentile": 0.0,
        }
        self.assertGreater(_base_interest_score(recent), _base_interest_score(quiet))

    def test_verified_github_repo_adds_a_weighted_priority_bonus(self):
        repo = {
            "stargazers_count": 1200,
            "forks_count": 180,
            "pushed_at": "2026-10-01T12:00:00Z",
            "archived": False,
        }
        self.assertGreaterEqual(_repository_interest_score([repo]), 25.0)
        self.assertEqual(_repository_interest_score([]), 0.0)

    def test_does_not_guess_code_repository(self):
        self.assertEqual(_extract_code_links("No official implementation is linked."), [])

    def test_extracts_explicit_github_url(self):
        html = '<p>Code: <a href="https://github.com/example/research-code">GitHub repository</a></p>'
        self.assertEqual(
            _extract_code_links(html),
            ["https://github.com/example/research-code"],
        )

    @patch("sources.papers.net.get_json")
    def test_repository_must_exist_and_readme_is_loaded(self, mock_get_json):
        mock_get_json.side_effect = [
            {
                "full_name": "example/research-code",
                "html_url": "https://github.com/example/research-code",
                "description": "Reference implementation",
                "default_branch": "main",
            },
            {
                "encoding": "base64",
                "content": base64.b64encode(b"# Research code\\nRun with Python.").decode("ascii"),
            },
        ]

        repositories = _verify_public_github_repositories(
            ["https://github.com/example/research-code"]
        )

        self.assertEqual(len(repositories), 1)
        self.assertEqual(repositories[0]["full_name"], "example/research-code")
        self.assertIn("Run with Python", repositories[0]["readme_excerpt"])
        self.assertEqual(mock_get_json.call_count, 2)

    def test_maps_arxiv_abstract_to_html(self):
        self.assertEqual(
            _arxiv_html_url("https://arxiv.org/abs/2401.12345v2"),
            "https://arxiv.org/html/2401.12345v2",
        )


    @patch("sources.papers.time.sleep")
    @patch("sources.papers.net.get_json", return_value={"results": []})
    def test_discovery_uses_supported_openalex_types(self, mock_get_json, mock_sleep):
        discover_candidates()
        self.assertGreater(mock_get_json.call_count, 0)
        for call in mock_get_json.call_args_list:
            self.assertEqual(
                call.kwargs["params"]["filter"],
                "type:article|preprint,is_retracted:false,from_publication_date:2019-01-01",
            )


if __name__ == "__main__":
    unittest.main()
