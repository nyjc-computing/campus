"""tests.flask_test.json_client

Test-compatible JsonClient that uses Flask test clients for routing.

This module provides a drop-in replacement for
campus.common.http.DefaultClient that uses Flask test clients for local
testing without actual HTTP calls.
"""

from typing import Any, Iterable, Mapping, Self
from urllib.parse import urljoin

import flask

from campus.common.http.interface import JsonDict, JsonResponse
from campus.common.http.errors import AuthenticationError
from campus.model import HttpHeader
from campus.common import env

from .response import FlaskTestResponse
from .campus_request import get_test_app


class TestJsonClient:
    """Test-compatible JsonClient using Flask test clients with routing.

    This class implements the JsonClient protocol and routes requests to
    the correct Flask app based on base_url and path prefix, using the
    same routing mechanism as TestCampusRequest.

    Key differences from FlaskTestClient:
    - Routes requests dynamically based on base_url and path prefix
    - Looks up Flask app from registry using get_test_app()
    - Compatible with DefaultClient interface used by AuditClient
    """

    # Type annotation to match JsonClient protocol
    # Note: In practice, this is always a string (base_url or ""), but
    # the protocol allows None for compatibility with DefaultClient
    base_url: str | None
    _timeout: int

    def __init__(
            self,
            base_url: str | None = None,
            *,
            auth: Iterable[str] | str | None = None,
            headers: Mapping[str, str] | None = None,
            **kwargs: Any
    ):
        """Initialize with base URL for routing.

        Args:
            base_url: Base URL for determining which app to use (e.g.,
                "https://campus.test")
            auth: Authentication credentials (ignored, uses env vars)
            headers: Default headers (ignored, uses env vars)
            **kwargs: Additional arguments (including timeout, ignored)
        """
        self.base_url = base_url or ""
        self._timeout = kwargs.get("timeout", 10)

    @property
    def _auth_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Loads from environment dynamically to ensure test isolation.
        This allows tests to change CLIENT_ID/CLIENT_SECRET between test classes.

        Returns:
            Dictionary of HTTP headers for authentication
        """
        return self._load_auth_headers()

    def _load_auth_headers(self) -> dict[str, str]:
        """Load authentication headers from environment variables.

        Note: Headers are loaded fresh on each access to ensure test
        isolation. This allows tests to change CLIENT_ID/CLIENT_SECRET
        between test classes.
        """
        # Try ACCESS_TOKEN first (Bearer auth)
        access_token = env.get("ACCESS_TOKEN")
        if access_token:
            return HttpHeader.from_bearer_token(access_token)

        # Try CLIENT_ID and CLIENT_SECRET (Basic auth)
        client_id = env.get("CLIENT_ID")
        client_secret = env.get("CLIENT_SECRET")
        if client_id and client_secret:
            return HttpHeader.from_credentials(client_id, client_secret)

        # Return empty headers for unauthenticated requests
        # (e.g., health checks, public endpoints)
        return {}

    def _get_app_for_request(self, path: str) -> flask.Flask:
        """Get the Flask app for a specific request path.

        Uses the test app registry to route to the correct app based on
        base_url and path prefix.

        Args:
            path: The request path

        Returns:
            The Flask app to handle this request
        """
        assert self.base_url
        app = get_test_app(self.base_url, path)
        if app is None:
            raise ValueError(
                f"No Flask app registered for base_url "
                f"{self.base_url!r} with path {path!r}. Use "
                "register_test_app() to register apps."
            )
        return app

    def _make_path(self, path: str) -> str:
        """Convert path to full URL if base_url is set, otherwise return
        path.
        """
        if self.base_url:
            return urljoin(self.base_url, path.lstrip('/'))
        return path

    def get(self: Self, path: str, params: JsonDict | None = None) -> JsonResponse:
        """Sends a GET request.

        Args:
            path: Request path
            params: Optional query parameters

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        app = self._get_app_for_request(path)
        test_client = app.test_client()
        full_path = self._make_path(path)

        response = test_client.get(
            full_path,
            query_string=params,
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def post(
            self: Self,
            path: str,
            json: JsonDict | None = None
    ) -> JsonResponse:
        """Sends a POST request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        app = self._get_app_for_request(path)
        test_client = app.test_client()
        full_path = self._make_path(path)

        response = test_client.post(
            full_path,
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def put(
            self: Self,
            path: str,
            json: JsonDict | None = None
    ) -> JsonResponse:
        """Sends a PUT request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        app = self._get_app_for_request(path)
        test_client = app.test_client()
        full_path = self._make_path(path)

        response = test_client.put(
            full_path,
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def delete(
            self: Self,
            path: str,
            json: JsonDict | None = None
    ) -> JsonResponse:
        """Sends a DELETE request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        app = self._get_app_for_request(path)
        test_client = app.test_client()
        full_path = self._make_path(path)

        response = test_client.delete(
            full_path,
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

    def patch(self: Self, path: str, json: Any = None) -> JsonResponse:
        """Sends a PATCH request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        app = self._get_app_for_request(path)
        test_client = app.test_client()
        full_path = self._make_path(path)

        response = test_client.patch(
            full_path,
            json=json,
            content_type='application/json',
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)


def patch_default_client() -> None:
    """Patch campus.common.http.DefaultClient to use TestJsonClient in
    integration tests.

    This function monkey-patches campus.common.http.DefaultClient
    with TestJsonClient, allowing all code using DefaultClient (like AuditClient)
    to use Flask test clients for testing without actual HTTP calls.

    Call this in test setup before any DefaultClient instances are
    created.
    """
    import campus.common.http

    # Store original for cleanup
    if not hasattr(campus.common.http, "_original_DefaultClient"):
        setattr(
            campus.common.http,
            "_original_DefaultClient",
            campus.common.http.DefaultClient
        )

    # Replace with test version
    campus.common.http.DefaultClient = TestJsonClient


def unpatch_default_client() -> None:
    """Restore original campus.common.http.DefaultClient.

    Call this in test teardown to clean up the monkey-patch.
    """
    import campus.common.http

    if hasattr(campus.common.http, "_original_DefaultClient"):
        campus.common.http.DefaultClient = getattr(
            campus.common.http,
            "_original_DefaultClient"
        )
        delattr(campus.common.http, "_original_DefaultClient")
