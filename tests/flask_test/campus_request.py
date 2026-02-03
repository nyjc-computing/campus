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


# Global registry for test apps
# Maps base_url to dict of path_prefix -> Flask app
# Example: {"https://campus.test": {"/auth": auth_app, "/api": api_app}}
_test_apps: dict[str, dict[str, flask.Flask]] = {}


def register_test_app(base_url: str, app: flask.Flask, path_prefix: str = "") -> None:
    """Register a Flask app for a given base URL in test mode.

    This allows TestCampusRequest to route requests to the correct Flask app
    based on the base_url and optionally the path prefix.

    Args:
        base_url: The base URL (e.g., "https://campus.test")
        app: The Flask application to handle requests
        path_prefix: Optional path prefix to route requests (e.g., "/auth", "/api")
    """
    if base_url not in _test_apps:
        _test_apps[base_url] = {}
    _test_apps[base_url][path_prefix] = app


def get_test_app(base_url: str, path: str = "") -> flask.Flask | None:
    """Get the registered Flask app for a given base URL and path.

    Args:
        base_url: The base URL to look up
        path: The request path (used for prefix-based routing)

    Returns:
        The Flask app if registered, None otherwise
    """
    if base_url not in _test_apps:
        return None

    apps_by_prefix = _test_apps[base_url]

    # If only one app registered for this base_url, return it
    if len(apps_by_prefix) == 1:
        return next(iter(apps_by_prefix.values()))

    # Try to match by path prefix
    for prefix, app in sorted(apps_by_prefix.items(), key=lambda x: -len(x[0])):
        if prefix and path.startswith(prefix):
            return app

    # Default to the app with no prefix
    return apps_by_prefix.get("", next(iter(apps_by_prefix.values())))


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
    - Looks up Flask app from registry based on base_url and request path
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

        # Override auth headers - if set, these take precedence over env vars
        # This allows set_bearer_authorization() to work for explicit token auth
        self._override_auth_headers: dict[str, str] | None = None

        # Don't look up app at init time - we'll determine it per-request
        # based on the path prefix
        # Get a default app for initialization
        app = self._get_app_for_base_url(self.base_url, "")
        if app is None:
            # Try to get any registered app
            if self.base_url in _test_apps and _test_apps[self.base_url]:
                app = next(iter(_test_apps[self.base_url].values()))
            else:
                raise ValueError(
                    f"No Flask app registered for base_url '{self.base_url}'. "
                    f"Use register_test_app() to register apps in test setup."
                )

        # Store the base_url for path-based routing
        # Initialize parent FlaskTestClient with a default app
        # We'll use the correct app per-request
        super().__init__(app, base_url=self.base_url)

    @property
    def _auth_headers(self) -> dict[str, str]:
        """Get authentication headers for requests.

        Returns override headers if set (via set_bearer_authorization etc.),
        otherwise loads dynamically from environment variables.

        This ensures test isolation - when env.CLIENT_ID changes between
        test classes, the new credentials are used automatically.

        Returns:
            Dictionary of HTTP headers for authentication
        """
        if self._override_auth_headers is not None:
            return self._override_auth_headers
        # Fall back to parent's dynamic loading from environment
        return super()._auth_headers  # type: ignore[bad-property-access]

    def _get_app_for_base_url(self, base_url: str, path: str = "") -> flask.Flask | None:
        """Get the Flask app for a given base URL and path.

        Uses path-based routing to determine the correct app.

        Args:
            base_url: The base URL to look up
            path: The request path (used for prefix-based routing)

        Returns:
            The Flask app if found, None otherwise
        """
        return get_test_app(base_url, path)

    def _get_app_for_request(self, path: str) -> flask.Flask:
        """Get the Flask app for a specific request path.

        Args:
            path: The request path

        Returns:
            The Flask app to handle this request
        """
        app = self._get_app_for_base_url(self.base_url, path)
        if app is None:
            raise ValueError(
                f"No Flask app registered for base_url '{self.base_url}' "
                f"with path '{path}'. Use register_test_app() to register apps."
            )
        return app

    def _make_path(self, path: str) -> str:
        """Convert path to full URL if base_url is set, otherwise return path."""
        if self.base_url:
            return urljoin(self.base_url, path.lstrip('/'))
        return path

    @property
    def headers(self) -> campus.model.HttpHeader:
        """Get the currently configured headers.

        Returns the headers that would be sent with requests.
        """
        # Reconstruct HttpHeader from current auth headers
        headers_dict = self._auth_headers
        if isinstance(headers_dict, dict):
            return campus.model.HttpHeader(**headers_dict)
        return headers_dict

    def set_basic_authorization(self, client_id: str, secret: str) -> None:
        """Set Basic Authorization header.

        Args:
            client_id: Client ID for basic auth
            secret: Client secret for basic auth
        """
        self._override_auth_headers = campus.model.HttpHeader.from_credentials(
            client_id, secret
        )  # HttpHeader is a dict

    def set_bearer_authorization(self, token: str) -> None:
        """Set Bearer Authorization header.

        Args:
            token: Bearer token
        """
        self._override_auth_headers = campus.model.HttpHeader.from_bearer_token(
            token
        )  # HttpHeader is a dict

    def reset_authorization(self) -> None:
        """Reset authorization back to client credentials from environment.

        This matches CampusRequest behavior - it resets to using the
        CLIENT_ID and CLIENT_SECRET from environment variables.

        After calling this, headers will be loaded dynamically from env,
        allowing tests to change credentials between test classes.
        """
        self._override_auth_headers = None  # Clear override, use env vars

    def get(self: Self, path: str, query: dict[str, Any] | None = None) -> FlaskTestResponse:
        """Sends a GET request.

        Args:
            path: Request path
            query: Optional query parameters

        Returns:
            FlaskTestResponse wrapping the test client response
        """
        app = self._get_app_for_request(path)
        test_client = app.test_client()
        full_path = self._make_path(path)

        response = test_client.get(
            full_path,
            query_string=query,
            headers=self._auth_headers
        )
        return FlaskTestResponse(response)

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
            json: dict[str, Any] | None = None
    ) -> FlaskTestResponse:
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
            json: dict[str, Any] | None = None
    ) -> FlaskTestResponse:
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

    def patch(
            self: Self,
            path: str,
            json: dict[str, Any] | None = None
    ) -> FlaskTestResponse:
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

    Also patches the module-level CampusRequest reference in campus_python
    since it imports CampusRequest directly at module level.

    Call this in test setup before any campus_python.Campus instances
    are created.
    """
    import campus_python.json_client
    import campus_python

    # Store original for cleanup
    if not hasattr(campus_python.json_client, "_original_CampusRequest"):
        campus_python.json_client._original_CampusRequest = (
            campus_python.json_client.CampusRequest
        )
    if not hasattr(campus_python, "_original_CampusRequest"):
        campus_python._original_CampusRequest = getattr(
            campus_python, "CampusRequest", None
        )

    # Replace with test version in both locations
    campus_python.json_client.CampusRequest = TestCampusRequest
    campus_python.CampusRequest = TestCampusRequest


def unpatch_campus_python() -> None:
    """Restore original campus_python.json_client.CampusRequest.

    Call this in test teardown to clean up the monkey-patch.
    """
    import campus_python.json_client
    import campus_python

    if hasattr(campus_python.json_client, "_original_CampusRequest"):
        campus_python.json_client.CampusRequest = (
            campus_python.json_client._original_CampusRequest
        )
        delattr(campus_python.json_client, "_original_CampusRequest")
    if hasattr(campus_python, "_original_CampusRequest"):
        if campus_python._original_CampusRequest is not None:
            campus_python.CampusRequest = campus_python._original_CampusRequest
        else:
            delattr(campus_python, "CampusRequest")
        delattr(campus_python, "_original_CampusRequest")
