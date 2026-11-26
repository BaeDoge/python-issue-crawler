import unittest
from unittest.mock import patch

from sources import web
from topics import troubleshooting


class TroubleshootingDiscoveryTests(unittest.TestCase):
    @patch.object(web, "TROUBLESHOOTING_TARGET_CANDIDATES", 2)
    @patch.object(web, "TROUBLESHOOTING_MAX_SEED_QUERIES", 3)
    @patch.object(web, "TROUBLESHOOTING_SEEDS_PER_RUN", 1)
    @patch.object(web, "TROUBLESHOOTING_PER_SEED", 1)
    @patch.object(web.random, "shuffle", lambda items: None)
    @patch.object(web, "stackoverflow_common_errors", return_value=[])
    @patch.object(web, "stackoverflow_for_seed")
    def test_searches_more_seeds_and_skips_history(self, search, _broad):
        search.side_effect = [
            [{"title": "Old topic", "link": "https://stackoverflow.com/questions/1/old"}],
            [{"title": "New topic A", "link": "https://stackoverflow.com/questions/2/new-a"}],
            [{"title": "New topic B", "link": "https://stackoverflow.com/questions/3/new-b"}],
        ]
        results = web.stackoverflow_seed_candidates(
            exclude_links={"https://stackoverflow.com/questions/1/old"}
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(search.call_count, 3)
        self.assertEqual([item["link"] for item in results], [
            "https://stackoverflow.com/questions/2/new-a",
            "https://stackoverflow.com/questions/3/new-b",
        ])

    @patch.object(web, "TROUBLESHOOTING_TARGET_CANDIDATES", 1)
    @patch.object(web, "TROUBLESHOOTING_MAX_SEED_QUERIES", 2)
    @patch.object(web, "TROUBLESHOOTING_SEEDS_PER_RUN", 1)
    @patch.object(web, "TROUBLESHOOTING_PER_SEED", 1)
    @patch.object(web.random, "shuffle", lambda items: None)
    @patch.object(web, "stackoverflow_common_errors", return_value=[])
    @patch.object(web, "stackoverflow_for_seed", side_effect=[[], [
        {"title": "TypeError: object is not callable", "link": "https://stackoverflow.com/questions/9/typeerror"}
    ]])
    def test_relaxes_filters_after_initial_seed(self, search, _broad):
        web.stackoverflow_seed_candidates()
        self.assertEqual(search.call_args_list[0].kwargs["min_score"], web.TROUBLESHOOTING_MIN_SCORE)
        self.assertEqual(search.call_args_list[1].kwargs["min_score"], max(0, min(5, web.TROUBLESHOOTING_MIN_SCORE)))
        self.assertTrue(search.call_args_list[1].kwargs["relaxed_title"])


    @patch.object(troubleshooting.net, "get_text")
    def test_pandas_topic_receives_current_official_cow_document(self, get_text):
        get_text.return_value = (
            "<h2>Previous behavior</h2><p>Views and copies had different behavior.</p>"
            "<h2>Migrating to Copy-on-Write</h2><p>Copy-on-Write is default in pandas 3.0.</p>"
            "<h2>Chained Assignment</h2><p>Use loc for a single assignment.</p>"
            "<h2>Read-only NumPy arrays</h2><p>Not part of this excerpt.</p>"
        )
        result = troubleshooting._load_official_reference({
            "title": "Correct way to set value on a slice in pandas"
        })
        self.assertEqual(result["platform"], "pandas 공식 문서")
        self.assertIn("Copy-on-Write is default in pandas 3.0", result["text"])
        self.assertNotIn("Not part of this excerpt", result["text"])
        get_text.assert_called_once_with(
            troubleshooting.PANDAS_COW_DOC_URL,
            timeout=15,
            quiet=True,
        )

    @patch.object(troubleshooting.net, "get_text")
    def test_unrelated_topic_does_not_fetch_pandas_docs(self, get_text):
        result = troubleshooting._load_official_reference({
            "title": "UnicodeDecodeError utf-8 codec can't decode byte"
        })
        self.assertEqual(result, {})
        get_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
