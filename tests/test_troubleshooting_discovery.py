import unittest
from unittest.mock import patch

from sources import web


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
    @patch.object(web, "stackoverflow_for_seed", return_value=[
        {"title": "TypeError: object is not callable", "link": "https://stackoverflow.com/questions/9/typeerror"}
    ])
    def test_relaxes_filters_after_initial_seed(self, search, _broad):
        web.stackoverflow_seed_candidates()
        self.assertEqual(search.call_args_list[0].kwargs["min_score"], web.TROUBLESHOOTING_MIN_SCORE)
        self.assertEqual(search.call_args_list[1].kwargs["min_score"], max(0, min(5, web.TROUBLESHOOTING_MIN_SCORE)))
        self.assertTrue(search.call_args_list[1].kwargs["relaxed_title"])


if __name__ == "__main__":
    unittest.main()
