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



    @patch.object(troubleshooting.net, "get_text")
    @patch.object(troubleshooting, "capture_images", return_value=[])
    @patch.object(troubleshooting, "blog_references", return_value=[])
    @patch.object(troubleshooting, "_load_official_reference", return_value={
        "platform": "pandas 공식 문서",
        "title": "Copy-on-Write (CoW)",
        "url": troubleshooting.PANDAS_COW_DOC_URL,
        "text": "Copy-on-Write was first introduced in version 1.5.0. The default is pandas 3.0.",
    })
    @patch.object(troubleshooting, "stackoverflow_answer_detail", return_value={
        "text": "The original DataFrame was likely sliced earlier. Use .copy() when creating the subset.",
        "raw_body": "",
        "author": "answerer",
    })
    def test_build_context_gives_question_answer_and_docs_to_verifier(
        self, _answer_detail, _official, _blogs, _images, _get_text
    ):
        chosen = {
            "title": "Python: Pandas Dataframe how to multiply entire column with a scalar",
            "link": "https://stackoverflow.com/questions/33768122/python-pandas-dataframe-how-to-multiply-entire-column-with-a-scalar",
            "meta": "StackOverflow · 2015 · pandas 0.16.2",
            "body_excerpt": (
                "df['quantity'] *= -1 gives SettingWithCopyWarning. "
                "The question author reports pandas 0.16.2."
            ),
            "author": "questioner",
            "raw_body": "",
        }
        result = troubleshooting._build_context(chosen)
        self.assertIn("df['quantity'] *= -1", result["context_text"])
        self.assertIn("df[['quantity']] 자체가 원문 경고를 재현한다고 지어내지 말 것", result["context_text"])
        self.assertIn("원문 질문/이슈 본문", result["review_context"])
        self.assertIn("채택 답변/해결 코멘트", result["review_context"])
        self.assertIn("Copy-on-Write was first introduced", result["review_context"])
        self.assertTrue(any(src["platform"] == "pandas 공식 문서" for src in result["sources"]))


if __name__ == "__main__":
    unittest.main()
