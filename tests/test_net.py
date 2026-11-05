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


if __name__ == "__main__":
    unittest.main()
