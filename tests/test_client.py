"""Test client implementations for Campus client interface.

Provides Flask test client and werkzeug TestResponse wrappers that implement
the JsonClient and JsonResponse protocols for testing purposes.

Example usage: see test_client_example_usage.py
"""

from typing import Any, Self, Callable
from urllib.parse import urlencode

from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from campus.client.interface import JsonClient, JsonResponse, JsonDict


class FlaskTestResponse(JsonResponse):
    """Response wrapper for werkzeug TestResponse, to conform to JsonResponse
    interface.
    """

    def __init__(self, response: TestResponse):
        self._response = response

    @property
    def status(self) -> int:
        """HTTP status code of the response."""
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        """Returns headers of the response as a dict."""
        # Convert werkzeug Headers to plain dict[str, str]
        return {k: v for k, v in self._response.headers.items()}

    @property
    def text(self) -> str:
        """Returns the response body as a string."""
        return self._response.get_data(as_text=True)

    def json(self) -> Any:
        """Returns the response body as JSON."""
        return self._response.get_json()


class FlaskTestClient(JsonClient):
    """
    HTTP client for testing Campus services using Flask's test client.

    This implementation wraps Flask's FlaskClient (test client) to provide
    the same interface as the production RequestsClient, enabling testing
    without making actual HTTP requests.
    """

    def __init__(self, flask_client: FlaskClient, base_url: str = ""):
        """
        Initialize the FlaskTestClient.

        Args:
            flask_client: Flask test client instance
            base_url: Base URL for the service (optional, mainly for compatibility)
        """
        self._flask_client = flask_client
        self.base_url = base_url

    def _make_request(
            self,
            method: str,
            path: str,
            params: JsonDict | None = None,
            json: JsonDict | None = None,
    ) -> FlaskTestResponse:
        """
        Make an HTTP request using the Flask test client.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path.
            params: Query parameters for GET requests.
            json: JSON body for POST/PUT/PATCH requests.

        Returns:
            FlaskTestResponse: A response wrapper object.
        """
        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path

        # Handle query parameters for GET requests
        if params and method.upper() == 'GET':
            query_string = urlencode(params)
            if '?' in path:
                path = f"{path}&{query_string}"
            else:
                path = f"{path}?{query_string}"

        # Make the request using the correct method
        if method.upper() == 'GET':
            response = self._flask_client.get(path)
        elif method.upper() == 'POST':
            response = self._flask_client.post(
                path,
                json=json,
                content_type='application/json'
            )
        elif method.upper() == 'PUT':
            response = self._flask_client.put(
                path,
                json=json,
                content_type='application/json'
            )
        elif method.upper() == 'PATCH':
            response = self._flask_client.patch(
                path,
                json=json,
                content_type='application/json'
            )
        elif method.upper() == 'DELETE':
            response = self._flask_client.delete(
                path,
                json=json,
                content_type='application/json'
            )
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        return FlaskTestResponse(response)

    def get(self: Self, path: str, params: JsonDict | None = None) -> JsonResponse:
        """Sends a GET request."""
        return self._make_request("GET", path, params=params)

    def post(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a POST request."""
        return self._make_request("POST", path, json=json)

    def put(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a PUT request."""
        return self._make_request("PUT", path, json=json)

    def patch(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a PATCH request."""
        return self._make_request("PATCH", path, json=json)

    def delete(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a DELETE request."""
        return self._make_request("DELETE", path, json=json)


def create_test_client_factory(flask_client: FlaskClient, base_url: str = "") -> Callable[[], JsonClient]:
    """
    Create a client factory function for testing.

    Args:
        flask_client: Flask test client instance
        base_url: Base URL for the service (optional)

    Returns:
        Callable that returns a FlaskTestClient instance
    """
    def factory() -> JsonClient:
        return FlaskTestClient(flask_client, base_url)

    return factory
