"""tests.flask_test.client

FlaskTestClient adapter for Campus JsonClient protocol.
"""

from typing import Any, Iterable, Mapping, Self
from urllib.parse import urljoin

import flask

from campus.common.http.interface import JsonDict, JsonResponse
from campus.common.http.errors import AuthenticationError
from campus.model import HttpHeader
from campus.common import env

from .response import FlaskTestResponse


class FlaskTestClient:
    """Adapter that wraps Flask test client to implement JsonClient protocol.

    This class adapts Flask's test client to match the Campus JsonClient interface,
    enabling seamless testing with Flask apps without actual HTTP requests.
    """

    def __init__(
            self,
            app: flask.Flask,
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

        # Load authentication from environment variables
        self._auth_headers = self._load_auth_headers()

        # Store app context for proper request handling
        self._app_context = None

    def _load_auth_headers(self) -> dict[str, str]:
        """Load authentication headers from environment variables."""
        # Try ACCESS_TOKEN first (Bearer auth)
        access_token = env.ACCESS_TOKEN
        if access_token:
            return HttpHeader.from_bearer_token(access_token)

        # Try CLIENT_ID and CLIENT_SECRET (Basic auth)
        client_id = env.CLIENT_ID
        client_secret = env.CLIENT_SECRET
        if client_id and client_secret:
            return HttpHeader.from_credentials(client_id, client_secret)

        # No credentials found - unauthenticated requests are not yet supported
        raise AuthenticationError(
            "Missing credentials. Set ACCESS_TOKEN or both CLIENT_ID and CLIENT_SECRET environment variables."
        )

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
            query_string=params,
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def post(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a POST request."""
        self._ensure_app_context()

        response = self._test_client.post(
            self._make_path(path),
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def put(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a PUT request."""
        self._ensure_app_context()

        response = self._test_client.put(
            self._make_path(path),
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def delete(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a DELETE request."""
        self._ensure_app_context()

        response = self._test_client.delete(
            self._make_path(path),
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def patch(self: Self, path: str, json: Any = None) -> JsonResponse:
        """Sends a PATCH request."""
        self._ensure_app_context()

        response = self._test_client.patch(
            self._make_path(path),
            json=json,
            content_type='application/json',
            headers=self._auth_headers
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
