import unittest

from sources.blogs import is_relevant_blog_article


class BlogRelevanceTests(unittest.TestCase):
    def setUp(self):
        self.query = "파이썬 Pandas DataFrame 열 곱셈 해결"
        self.context = (
            "Python pandas DataFrame df['quantity'] *= -1 "
            "SettingWithCopyWarning pandas 0.16.2 sliced from parent DataFrame"
        )

    def test_rejects_different_pandas_value_error(self):
        self.assertFalse(is_relevant_blog_article(
            query=self.query,
            relevance_context=self.context,
            title="pandas DataFrame: ValueError If using all scalar values",
            text="ValueError: If using all scalar values, you must pass an index.",
        ))

    def test_rejects_generic_series_dataframe_article(self):
        self.assertFalse(is_relevant_blog_article(
            query=self.query,
            relevance_context=self.context,
            title="Python pandas Series and DataFrame basics",
            text="An introduction to Series, DataFrame, rows and columns.",
        ))

    def test_accepts_article_about_the_same_warning_or_concept(self):
        self.assertTrue(is_relevant_blog_article(
            query=self.query,
            relevance_context=self.context,
            title="SettingWithCopyWarning과 chained assignment 정리",
            text="슬라이스와 복사본, 뷰와 복사본의 차이를 설명합니다.",
        ))

    def test_requires_exact_marker_for_other_exceptions(self):
        self.assertFalse(is_relevant_blog_article(
            query="python TypeError unhashable type dict",
            relevance_context="TypeError: unhashable type: dict",
            title="Python ValueError invalid literal",
            text="ValueError: invalid literal for int().",
        ))


if __name__ == "__main__":
    unittest.main()
