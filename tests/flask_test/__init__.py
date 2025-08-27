"""tests.flask_test

Provides Flask test client and werkzeug TestResponse wrappers that implement
the JsonClient and JsonResponse protocols for testing purposes.

Example usage: see test_client_example_usage.py
"""

from typing import Any, Literal, Self

from flask import Flask
from werkzeug.test import TestResponse

from campus.client.interface import JsonClient, JsonResponse, JsonDict

from .interface import FlaskClientInterface


def configure_test_app(app: Flask) -> Flask:
    """
    Configure a Flask application for testing.

    Returns:
        Flask: The configured Flask application instance
    """
    app.testing = True
    return app


def create_test_client(app: Flask) -> "FlaskTestClient":
    """Create a wrapped test client from a Flask app.

    Args:
        app: Flask application instance

    Returns:
        FlaskTestClient instance
    """
    return FlaskTestClient(app.test_client())


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
        return dict(self._response.headers)

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
    # The test client routes requests directly to the attached application
    # and does not involve the network stack.
    # The placeholder base_url keeps the interface compatible with JsonClient
    # but is not actually used.
    base_url = "campus.localhost"
    # pylint: disable=missing-function-docstring

    def __init__(self, flask_client: FlaskClientInterface):
        """
        Initialize the FlaskTestClient.

        Args:
            flask_client: Flask test client instance
        """
        self._flask_client = flask_client

    def _make_request(
            self,
            method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
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
        assert method.isupper(), "HTTP method must be uppercase"
        assert path.startswith('/'), "Path must start with '/'"

        match method:
            case "GET":
                response = self._flask_client.get(path, query_string=params)
            case "POST":
                response = self._flask_client.post(path, json=json)
            case "PUT":
                response = self._flask_client.put(path, json=json)
            case "PATCH":
                response = self._flask_client.patch(path, json=json)
            case "DELETE":
                response = self._flask_client.delete(path, json=json)
            case _:
                raise ValueError(f"Unsupported HTTP method: {method}")
        return FlaskTestResponse(response)

    def get(self: Self, path: str, params: JsonDict | None = None) -> FlaskTestResponse:
        return self._make_request("GET", path, params=params)

    def post(self: Self, path: str, json: JsonDict | None = None) -> FlaskTestResponse:
        return self._make_request("POST", path, json=json)

    def put(self: Self, path: str, json: JsonDict | None = None) -> FlaskTestResponse:
        return self._make_request("PUT", path, json=json)

    def patch(self: Self, path: str, json: JsonDict | None = None) -> FlaskTestResponse:
        return self._make_request("PATCH", path, json=json)

    def delete(self: Self, path: str, json: JsonDict | None = None) -> FlaskTestResponse:
        return self._make_request("DELETE", path, json=json)
