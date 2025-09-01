"""tests/unit/client/test_interface

Unit tests for the JsonClient and JsonResponse interfaces.
Tests the Protocol definitions without external dependencies.
"""

import unittest
from unittest.mock import Mock

from campus.common.http import JsonClient, JsonResponse


class TestJsonClientInterface(unittest.TestCase):
    """Test cases for JsonClient Protocol interface."""

    def test_protocol_methods_exist(self):
        """Test that JsonClient protocol defines required methods."""
        # Test that the protocol has the expected methods
        self.assertTrue(hasattr(JsonClient, '__annotations__'))

        # We can't instantiate a Protocol directly, but we can verify
        # that classes implementing it have the required methods
        mock_client = Mock(spec=JsonClient)

        # Verify all required methods exist
        self.assertTrue(hasattr(mock_client, 'get'))
        self.assertTrue(hasattr(mock_client, 'post'))
        self.assertTrue(hasattr(mock_client, 'put'))
        self.assertTrue(hasattr(mock_client, 'delete'))
        self.assertTrue(hasattr(mock_client, 'patch'))

        # base_url is an attribute, set it directly
        mock_client.base_url = "https://example.com"
        self.assertEqual(mock_client.base_url, "https://example.com")

    def test_mock_client_methods(self):
        """Test that mocked client methods can be called with expected signatures."""
        mock_client = Mock(spec=JsonClient)
        mock_response = Mock(spec=JsonResponse)

        # Configure mock methods
        mock_client.get.return_value = mock_response
        mock_client.post.return_value = mock_response
        mock_client.put.return_value = mock_response
        mock_client.delete.return_value = mock_response
        mock_client.patch.return_value = mock_response

        # Test method calls with expected parameters
        result = mock_client.get("/test", params={"key": "value"})
        self.assertEqual(result, mock_response)
        mock_client.get.assert_called_once_with(
            "/test", params={"key": "value"})

        result = mock_client.post("/test", json={"data": "value"})
        self.assertEqual(result, mock_response)
        mock_client.post.assert_called_once_with(
            "/test", json={"data": "value"})


class TestJsonResponseInterface(unittest.TestCase):
    """Test cases for JsonResponse Protocol interface."""

    def test_protocol_methods_exist(self):
        """Test that JsonResponse protocol defines required methods."""
        mock_response = Mock(spec=JsonResponse)

        # Verify all required methods/properties exist
        self.assertTrue(hasattr(mock_response, 'status_code'))
        self.assertTrue(hasattr(mock_response, 'headers'))
        self.assertTrue(hasattr(mock_response, 'text'))
        self.assertTrue(hasattr(mock_response, 'json'))
        self.assertTrue(hasattr(mock_response, 'ok'))
        self.assertTrue(hasattr(mock_response, 'client_error'))
        self.assertTrue(hasattr(mock_response, 'server_error'))

    def test_mock_response_properties(self):
        """Test that mocked response properties work as expected."""
        mock_response = Mock(spec=JsonResponse)

        # Configure mock properties
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"message": "success"}'
        mock_response.json.return_value = {"message": "success"}
        mock_response.ok.return_value = True
        mock_response.client_error.return_value = False
        mock_response.server_error.return_value = False

        # Test property access
        self.assertEqual(mock_response.status_code, 200)
        self.assertEqual(
            mock_response.headers["content-type"], "application/json")
        self.assertEqual(mock_response.text, '{"message": "success"}')
        self.assertEqual(mock_response.json(), {"message": "success"})
        self.assertTrue(mock_response.ok())
        self.assertFalse(mock_response.client_error())
        self.assertFalse(mock_response.server_error())


if __name__ == '__main__':
    unittest.main()
