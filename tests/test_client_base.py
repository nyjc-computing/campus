"""tests/test_client_base

Comprehensive unit tests for the core HTTP client functionality that underlies
all campus client libraries. Tests cover:

- HTTP method wrappers (GET, POST, PUT, PATCH, DELETE)
- Authentication schemes (basic auth, bearer tokens)
- Error handling and status code processing
- Request/response data transformation
- Environment-based credential loading

Testing Approach:
- **Direct unit testing**: Tests HttpClient as a standalone component
- **Mock external dependencies**: Uses unittest.mock for HTTP library calls
- **Isolated functionality**: Each test focuses on specific HttpClient behavior
- **Error scenario coverage**: Validates error handling across HTTP status codes

This foundational client is used by all other campus clients (vault, apps),
so comprehensive testing ensures reliability across the entire client library.
"""

import json
import os
import unittest
from unittest.mock import Mock, patch

from campus.client.base import HttpClient
from campus.client.errors import (
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError,
    MalformedResponseError,
    ConflictError
)


class TestHttpClient(unittest.TestCase):
    """Test cases for HttpClient class."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear environment variables
        if 'CLIENT_ID' in os.environ:
            del os.environ['CLIENT_ID']
        if 'CLIENT_SECRET' in os.environ:
            del os.environ['CLIENT_SECRET']

        self.base_url = "https://api.example.com"

    def tearDown(self):
        """Clean up after tests."""
        # Clear environment variables
        if 'CLIENT_ID' in os.environ:
            del os.environ['CLIENT_ID']
        if 'CLIENT_SECRET' in os.environ:
            del os.environ['CLIENT_SECRET']

    def test_init_with_base_url(self):
        """Test HttpClient initialization with base URL."""
        client = HttpClient(self.base_url)
        self.assertEqual(client.base_url, self.base_url)
        self.assertEqual(client.auth_scheme, "basic")

    def test_init_with_bearer_auth(self):
        """Test HttpClient initialization with bearer auth scheme."""
        client = HttpClient(self.base_url, auth_scheme="bearer")
        self.assertEqual(client.auth_scheme, "bearer")

    def test_init_loads_credentials_from_env(self):
        """Test that credentials are loaded from environment variables."""
        os.environ['CLIENT_ID'] = 'test_id'
        os.environ['CLIENT_SECRET'] = 'test_secret'

        client = HttpClient(self.base_url)
        self.assertEqual(client._client_id, 'test_id')
        self.assertEqual(client._client_secret, 'test_secret')

    def test_set_credentials_explicitly(self):
        """Test setting credentials explicitly."""
        client = HttpClient(self.base_url)
        client.set_credentials('explicit_id', 'explicit_secret')

        self.assertEqual(client._client_id, 'explicit_id')
        self.assertEqual(client._client_secret, 'explicit_secret')
        # Note: _access_token gets set when credentials are set
        self.assertIsNotNone(client._access_token)

    def test_ensure_authenticated_with_credentials(self):
        """Test authentication when credentials are available."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Should not raise
        client._ensure_authenticated()
        self.assertIsNotNone(client._access_token)

    def test_ensure_authenticated_without_credentials(self):
        """Test authentication fails when no credentials available."""
        client = HttpClient(self.base_url)

        with self.assertRaises(AuthenticationError) as context:
            client._ensure_authenticated()

        self.assertIn("No credentials available", str(context.exception))

    @patch('campus.common.utils.secret.encode_http_basic_auth')
    def test_get_headers_basic_auth(self, mock_encode):
        """Test header generation for basic auth."""
        mock_encode.return_value = "Basic dGVzdF9pZDp0ZXN0X3NlY3JldA=="

        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        headers = client._get_headers()

        expected_headers = {
            "Authorization": "Basic dGVzdF9pZDp0ZXN0X3NlY3JldA==",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.assertEqual(headers, expected_headers)
        # Should be called twice: once during set_credentials, once during _get_headers call
        self.assertEqual(mock_encode.call_count, 2)

    def test_get_headers_bearer_auth(self):
        """Test header generation for bearer auth."""
        client = HttpClient(self.base_url, auth_scheme="bearer")
        client.set_credentials('test_id', 'test_secret')

        headers = client._get_headers()

        expected_headers = {
            "Authorization": f"Bearer token_for_test_id",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.assertEqual(headers, expected_headers)

    def test_get_headers_invalid_auth_scheme(self):
        """Test header generation with invalid auth scheme."""
        client = HttpClient(self.base_url, auth_scheme="invalid")
        # Don't set credentials first - this will fail when they try to update session headers

        with self.assertRaises(ValueError) as context:
            client.set_credentials('test_id', 'test_secret')

        self.assertIn("Unknown authentication scheme", str(context.exception))

    def test_make_request_success(self):
        """Test successful HTTP request."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.content = b'{"result": "success"}'
        mock_response.json.return_value = {"result": "success"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client._make_request('GET', '/test')

        self.assertEqual(result, {"result": "success"})
        mock_session.request.assert_called_once()

    def test_make_request_empty_response(self):
        """Test HTTP request with empty response."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.content = b''
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client._make_request('GET', '/test')

        self.assertEqual(result, {})

    def test_make_request_validation_error_400(self):
        """Test HTTP request with 400 validation error."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.ok = False
        mock_response.json.return_value = {"error": "Invalid input"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(ValidationError):
            client._make_request('POST', '/test', {"invalid": "data"})

    def test_make_request_authentication_error_401(self):
        """Test HTTP request with 401 authentication error."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.ok = False
        mock_response.json.return_value = {"error": "Unauthorized"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(AuthenticationError):
            client._make_request('GET', '/secure')

    def test_make_request_access_denied_error_403(self):
        """Test HTTP request with 403 access denied error."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.ok = False
        mock_response.json.return_value = {"error": "Forbidden"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(AccessDeniedError):
            client._make_request('GET', '/forbidden')

    def test_make_request_not_found_error_404(self):
        """Test HTTP request with 404 not found error."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.ok = False
        mock_response.json.return_value = {"error": "Not found"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(NotFoundError):
            client._make_request('GET', '/nonexistent')

    def test_make_request_conflict_error_409(self):
        """Test HTTP request with 409 conflict error."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.ok = False
        mock_response.json.return_value = {"error": "Conflict"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(ConflictError):
            client._make_request('POST', '/conflict')

    def test_make_request_server_error_500(self):
        """Test HTTP request with 500 server error."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.ok = False
        mock_response.text = "Internal Server Error"
        mock_response.headers = {"content-type": "text/html"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(NetworkError) as context:
            client._make_request('GET', '/error')

        self.assertIn("HTTP 500", str(context.exception))

    def test_make_request_malformed_json(self):
        """Test HTTP request with malformed JSON response."""
        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        # Mock the session after client initialization
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.content = b'{"invalid": json}'
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_session.request.return_value = mock_response
        client.session = mock_session

        with self.assertRaises(MalformedResponseError):
            client._make_request('GET', '/malformed')

    @patch('campus.client.base.HttpClient._make_request')
    def test_get_method(self, mock_make_request):
        """Test GET method wrapper."""
        mock_make_request.return_value = {"data": "test"}

        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        result = client.get('/test', params={'key': 'value'})

        mock_make_request.assert_called_once_with(
            'GET', '/test', params={'key': 'value'})
        self.assertEqual(result, {"data": "test"})

    @patch('campus.client.base.HttpClient._make_request')
    def test_post_method(self, mock_make_request):
        """Test POST method wrapper."""
        mock_make_request.return_value = {"created": True}

        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        data = {"name": "test"}
        result = client.post('/create', data, params={'key': 'value'})

        mock_make_request.assert_called_once_with(
            'POST', '/create', data=data, params={'key': 'value'})
        self.assertEqual(result, {"created": True})

    @patch('campus.client.base.HttpClient._make_request')
    def test_put_method(self, mock_make_request):
        """Test PUT method wrapper."""
        mock_make_request.return_value = {"updated": True}

        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        data = {"name": "updated"}
        result = client.put('/update', data)

        mock_make_request.assert_called_once_with(
            'PUT', '/update', data=data, params=None)
        self.assertEqual(result, {"updated": True})

    @patch('campus.client.base.HttpClient._make_request')
    def test_patch_method(self, mock_make_request):
        """Test PATCH method wrapper."""
        mock_make_request.return_value = {"patched": True}

        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        data = {"field": "new_value"}
        result = client.patch('/patch', data)

        mock_make_request.assert_called_once_with(
            'PATCH', '/patch', data=data, params=None)
        self.assertEqual(result, {"patched": True})

    @patch('campus.client.base.HttpClient._make_request')
    def test_delete_method(self, mock_make_request):
        """Test DELETE method wrapper."""
        mock_make_request.return_value = {"deleted": True}

        client = HttpClient(self.base_url)
        client.set_credentials('test_id', 'test_secret')

        result = client.delete('/delete', params={'id': '123'})

        mock_make_request.assert_called_once_with(
            'DELETE', '/delete', params={'id': '123'})
        self.assertEqual(result, {"deleted": True})


if __name__ == '__main__':
    unittest.main()
