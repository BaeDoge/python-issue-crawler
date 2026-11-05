import unittest
from unittest.mock import Mock, patch

from sources import net


class RequestParamsTests(unittest.TestCase):
    @patch("sources.net.requests.request")
    def test_request_forwards_query_params(self, mock_request):
        response = Mock(status_code=200)
        mock_request.return_value = response
        params = {"search": "large language models", "per-page": 20}

        result = net.request("GET", "https://api.openalex.org/works", params=params)

        self.assertIs(result, response)
        self.assertEqual(mock_request.call_args.kwargs["params"], params)


    @patch("sources.net.time.sleep")
    @patch("sources.net.requests.request")
    def test_request_retries_http_429_once(self, mock_request, mock_sleep):
        limited = Mock(status_code=429, headers={}, text='Please retry in 0s')
        success = Mock(status_code=200)
        mock_request.side_effect = [limited, success]

        result = net.request("GET", "https://api.openalex.org/works", params={"search": "AI"})

        self.assertIs(result, success)
        self.assertEqual(mock_request.call_count, 2)
        mock_sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
