"""tests.flask_test.client

FlaskTestClient adapter for Campus JsonClient protocol.
"""

from typing import Any, Iterable, Mapping, Self
from urllib.parse import urljoin

from flask import Flask
from flask.testing import FlaskClient

from campus.common.http.interface import JsonDict, JsonResponse
from .response import FlaskTestResponse


class FlaskTestClient:
    """Adapter that wraps Flask test client to implement JsonClient protocol.

    This class adapts Flask's test client to match the Campus JsonClient interface,
    enabling seamless testing with Flask apps without actual HTTP requests.
    """

    def __init__(
            self,
            app: Flask,
            base_url: str | None = None,
            *,
            auth: Iterable[str] | str | None = None,
            headers: Mapping[str, str] | None = None,
            **kwargs: Any
    ):
        """Initialize with a Flask app for testing.

        Args:
            app: The Flask application to test
            base_url: Base URL for the client (for compatibility)
            auth: Authentication (ignored for Flask test client)
            headers: Default headers (ignored for Flask test client)
            **kwargs: Additional arguments (ignored)
        """
        self.app = app
        self.base_url = base_url
        self._test_client = app.test_client()

        # Store app context for proper request handling
        self._app_context = None

    def _ensure_app_context(self):
        """Ensure we have an active app context."""
        if self._app_context is None:
            self._app_context = self.app.app_context()
            self._app_context.push()

    def _make_path(self, path: str) -> str:
        """Convert path to full URL if base_url is set, otherwise return path."""
        if self.base_url:
            return urljoin(self.base_url, path.lstrip('/'))
        return path

    def get(self: Self, path: str, params: JsonDict | None = None) -> JsonResponse:
        """Sends a GET request."""
        self._ensure_app_context()

        response = self._test_client.get(
            self._make_path(path),
            query_string=params
        )
        return FlaskTestResponse(response)

    def post(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a POST request."""
        self._ensure_app_context()

        response = self._test_client.post(
            self._make_path(path),
            json=json,
            content_type='application/json'
        )
        return FlaskTestResponse(response)

    def put(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a PUT request."""
        self._ensure_app_context()

        response = self._test_client.put(
            self._make_path(path),
            json=json,
            content_type='application/json'
        )
        return FlaskTestResponse(response)

    def delete(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a DELETE request."""
        self._ensure_app_context()

        response = self._test_client.delete(
            self._make_path(path),
            json=json,
            content_type='application/json'
        )
        return FlaskTestResponse(response)

    def patch(self: Self, path: str, json: Any = None) -> JsonResponse:
        """Sends a PATCH request."""
        self._ensure_app_context()

        response = self._test_client.patch(
            self._make_path(path),
            json=json,
            content_type='application/json'
        )
        return FlaskTestResponse(response)

    def close(self):
        """Clean up app context."""
        if self._app_context is not None:
            self._app_context.pop()
            self._app_context = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
