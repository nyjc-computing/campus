"""tests.flask_test.campus_request

Test-compatible CampusRequest that uses FlaskTestClient.

This module provides a drop-in replacement for campus_python.json_client.CampusRequest
that uses FlaskTestClient for local testing without actual HTTP calls.
"""

from typing import Any, Self
from urllib.parse import urljoin

import flask
import campus.model

from .client import FlaskTestClient
from .response import FlaskTestResponse


# Global registry mapping base URLs to Flask apps for test mode
_test_apps: dict[str, flask.Flask] = {}


def register_test_app(base_url: str, app: flask.Flask) -> None:
    """Register a Flask app for a given base URL in test mode.

    This allows TestCampusRequest to route requests to the correct Flask app
    based on the base_url.

    Args:
        base_url: The base URL (e.g., "https://campus.auth" or "https://campus.api")
        app: The Flask application to handle requests for this base URL
    """
    _test_apps[base_url] = app


def get_test_app(base_url: str) -> flask.Flask | None:
    """Get the registered Flask app for a given base URL.

    Args:
        base_url: The base URL to look up

    Returns:
        The Flask app if registered, None otherwise
    """
    return _test_apps.get(base_url)


def clear_test_apps() -> None:
    """Clear all registered test apps."""
    _test_apps.clear()


class TestCampusRequest(FlaskTestClient):
    """Test-compatible CampusRequest using FlaskTestClient.

    This class extends FlaskTestClient to implement the full CampusRequest
    interface from campus_python.json_client, allowing it to be used as
    a drop-in replacement during testing.

    Key differences from FlaskTestClient:
    - Implements set_basic_authorization() and set_bearer_authorization()
    - Exposes headers property
    - Looks up Flask app from registry based on base_url
    """

    def __init__(
            self,
            base_url: str | None = None,
            *,
            headers: dict[str, str] | None = None,
            **kwargs: Any
    ):
        """Initialize with a Flask app for testing.

        Args:
            base_url: Base URL for determining which app to use
            headers: Default headers (for compatibility, ignored in favor of env)
            **kwargs: Additional arguments (including timeout, ignored)
        """
        self.base_url = base_url or ""
        self._timeout = kwargs.get("timeout", 10)

        # Look up the Flask app from registry
        app = self._get_app_for_base_url(self.base_url)
        if app is None:
            raise ValueError(
                f"No Flask app registered for base_url '{self.base_url}'. "
                f"Use register_test_app() to register apps in test setup."
            )

        # Initialize parent FlaskTestClient with the resolved app
        super().__init__(app, base_url=self.base_url)

    def _get_app_for_base_url(self, base_url: str) -> flask.Flask | None:
        """Get the Flask app for a given base URL.

        Attempts to match the base_url against registered test apps.
        Handles both full matches and partial matches (e.g., "https://campus.auth"
        will match "https://campus.auth").

        Args:
            base_url: The base URL to look up

        Returns:
            The Flask app if found, None otherwise
        """
        # Try exact match first
        if base_url in _test_apps:
            return _test_apps[base_url]

        # Try matching without trailing slash
        if base_url.endswith("/"):
            base_url = base_url[:-1]
            if base_url in _test_apps:
                return _test_apps[base_url]

        # Try finding by key that starts with base_url
        for key, app in _test_apps.items():
            if key.startswith(base_url) or base_url.startswith(key):
                return app

        return None

    @property
    def headers(self) -> campus.model.HttpHeader:
        """Get the currently configured headers.

        Returns the headers that would be sent with requests.
        """
        # Reconstruct HttpHeader from current auth headers
        return campus.model.HttpHeader(**self._auth_headers)

    def set_basic_authorization(self, client_id: str, secret: str) -> None:
        """Set Basic Authorization header.

        Args:
            client_id: Client ID for basic auth
            secret: Client secret for basic auth
        """
        self._auth_headers = campus.model.HttpHeader.from_credentials(
            client_id, secret
        )

    def set_bearer_authorization(self, token: str) -> None:
        """Set Bearer Authorization header.

        Args:
            token: Bearer token
        """
        self._auth_headers = campus.model.HttpHeader.from_bearer_token(token)

    def reset_authorization(self) -> None:
        """Reset authorization back to client credentials from environment.

        This matches CampusRequest behavior - it resets to using the
        CLIENT_ID and CLIENT_SECRET from environment variables.
        """
        from campus.common import env

        env.require("CLIENT_ID", "CLIENT_SECRET")
        self._auth_headers = campus.model.HttpHeader.from_credentials(
            env.CLIENT_ID,
            env.CLIENT_SECRET
        )

    def get(self: Self, path: str, query: dict[str, Any] | None = None) -> FlaskTestResponse:
        """Sends a GET request.

        Args:
            path: Request path
            query: Optional query parameters

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        return super().get(path, params=query)

    def post(
            self: Self,
            path: str,
            json: dict[str, Any] | None = None
    ) -> FlaskTestResponse:
        """Sends a POST request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        return super().post(path, json=json)

    def put(
            self: Self,
            path: str,
            json: dict[str, Any] | None = None
    ) -> FlaskTestResponse:
        """Sends a PUT request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        return super().put(path, json=json)

    def delete(
            self: Self,
            path: str,
            json: dict[str, Any] | None = None
    ) -> FlaskTestResponse:
        """Sends a DELETE request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        return super().delete(path, json=json)

    def patch(self: Self, path: str, json: Any = None) -> FlaskTestResponse:
        """Sends a PATCH request.

        Args:
            path: Request path
            json: Optional JSON body

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        return super().patch(path, json=json)


def patch_campus_python() -> None:
    """Patch campus_python to use TestCampusRequest in tests.

    This function monkey-patches campus_python.json_client.CampusRequest
    with TestCampusRequest, allowing all Campus client code to use
    FlaskTestClient for testing without actual HTTP calls.

    Call this in test setup before any campus_python.Campus instances
    are created.
    """
    import campus_python.json_client

    # Store original for cleanup
    if not hasattr(campus_python.json_client, "_original_CampusRequest"):
        campus_python.json_client._original_CampusRequest = (
            campus_python.json_client.CampusRequest
        )

    # Replace with test version
    campus_python.json_client.CampusRequest = TestCampusRequest


def unpatch_campus_python() -> None:
    """Restore original campus_python.json_client.CampusRequest.

    Call this in test teardown to clean up the monkey-patch.
    """
    import campus_python.json_client

    if hasattr(campus_python.json_client, "_original_CampusRequest"):
        campus_python.json_client.CampusRequest = (
            campus_python.json_client._original_CampusRequest
        )
        delattr(campus_python.json_client, "_original_CampusRequest")
