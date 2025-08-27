"""tests.flask_test

Provides Flask test client and werkzeug TestResponse wrappers that implement
the JsonClient and JsonResponse protocols for testing purposes.

Example usage: see test_client_example_usage.py
"""

from typing import Any, Callable, Iterable, Literal, Mapping, Self

from flask import Flask
from werkzeug.test import TestResponse

from campus.common import devops
from campus.common.http import JsonClient, JsonDict, JsonResponse
from campus.common.utils import secret

from .interface import FlaskClientInterface


def configure_test_app(app: Flask) -> Flask:
    """
    Configure a Flask application for testing.

    Returns:
        Flask: The configured Flask application instance
    """
    app.testing = True
    return app


def create_client_factory(app: Flask) -> Callable[[], "FlaskTestClient"]:
    """Create a client factory for the given Flask app.

    This function is meant to hook into campus.common.http.client_factory

    Args:
        app: Flask application instance

    Returns:
        ClientFactory: A factory for creating test clients
    """
    def get_client(*args, **kwargs) -> "FlaskTestClient":
        return FlaskTestClient(
            *args,
            **kwargs,
            flask_client=app.test_client()
        )
    return get_client


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
    # pylint: disable=missing-function-docstring

    def __init__(
            self,
            # The placeholder base_url is not actually used.
            base_url: str = "campus.localhost",
            *,
            flask_client: FlaskClientInterface,
            auth: Iterable[str] | str | None = None,
            headers: Mapping[str, str] | None = None,
            **kwargs: Any
    ):
        """Initialize the FlaskTestClient."""
        self.base_url = base_url
        self.headers = {}
        auth = auth or devops.load_credentials_from_env()
        match auth:
            case (client_id, client_secret):
                self.headers['Authorization'] = secret.encode_http_basic_auth(
                    client_id,
                    client_secret
                )
            case str():
                self.headers['Authorization'] = f"Bearer {auth}"
            case _:
                raise ValueError(f"Unknown auth {auth!r}")
        self.headers["Content-Type"] = "application/json"
        self.headers["Accept"] = "application/json"
        self.headers.update(headers or {})
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


__all__ = [
    "FlaskTestClient",
    "FlaskTestResponse",
    "create_client_factory",
    "configure_test_app",
]
