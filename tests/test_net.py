import unittest
from unittest.mock import Mock, patch

from sources import net


class SharedRequestTests(unittest.TestCase):
    @patch.object(net.requests, "request")
    def test_forwards_query_params_to_requests(self, request):
        response = Mock()
        response.status_code = 200
        request.return_value = response
        params = {"search": "large language models", "per-page": 20}

        result = net.request("GET", "https://api.openalex.org/works", params=params)

        self.assertIs(result, response)
        self.assertEqual(request.call_args.kwargs["params"], params)


if __name__ == "__main__":
    unittest.main()
