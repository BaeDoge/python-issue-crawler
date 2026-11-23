import unittest
from unittest.mock import Mock, patch

import llm_diagnostics


class LlmDiagnosticsTests(unittest.TestCase):
    def test_http_status_classification(self):
        self.assertEqual(llm_diagnostics.classify_http_status(200), "ok")
        self.assertEqual(llm_diagnostics.classify_http_status(401), "authentication_or_permission")
        self.assertEqual(llm_diagnostics.classify_http_status(429), "rate_limit_or_quota")
        self.assertEqual(llm_diagnostics.classify_http_status(503), "temporary_upstream_failure")

    @patch("llm_diagnostics.requests.post")
    def test_success_probe_does_not_return_generated_text(self, post):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.headers = {"x-request-id": "request-123"}
        response.json.return_value = {
            "model": "local/qwen-test",
            "choices": [{"message": {"content": "BLOG_API_OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 3},
        }
        post.return_value = response

        result = llm_diagnostics._probe_model("local/qwen-test", ["writer"])

        self.assertEqual(result["status"], "ok")
        self.assertIsNotNone(result["latency_ms"])
        self.assertEqual(result["prompt_tokens"], 8)
        self.assertNotIn("content", result)
        self.assertNotIn("BLOG_API_OK", str(result))

    @patch("llm_diagnostics.requests.post")
    def test_rate_limit_probe_is_reported(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 429
        response.headers = {}
        response.json.return_value = {"error": {"message": "rate limit exceeded"}}
        post.return_value = response

        result = llm_diagnostics._probe_model("openrouter/test:free", ["custom"])

        self.assertEqual(result["status"], "rate_limit_or_quota")
        self.assertEqual(result["http_status"], 429)
        self.assertIn("rate limit", result["error"])


if __name__ == "__main__":
    unittest.main()
