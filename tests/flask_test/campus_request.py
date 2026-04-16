"""tests.flask_test.campus_request

Test-compatible JsonClient that routes requests to Flask test clients.

This module provides a drop-in replacement for campus_python.json_client.CampusRequest
that routes requests to the appropriate Flask app based on base_url and path prefix,
using Flask test clients for local testing without actual HTTP calls.

Key features:
- Does NOT require Flask app at initialization time
- Looks up apps from global registry at request time
- Implements full JsonClient protocol including auth methods
- Supports routing to multiple Flask apps by base_url and path prefix
"""

from typing import Any, Self
from urllib.parse import urljoin

import flask
import campus.model
from campus_python.json_client.interface import JsonClient

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


class TestCampusRequest(JsonClient):
    """Test-compatible JsonClient that routes to Flask test clients.

    This class implements the campus_python.json_client.JsonClient protocol
    and routes requests to the appropriate Flask app based on base_url and
    path prefix, using Flask test clients for local testing.

    Key differences from CampusRequest:
    - Does NOT require Flask app at initialization time
    - Routes requests dynamically based on base_url and path prefix
    - Looks up Flask app from registry using get_test_app()
    - Compatible with JsonClient protocol used by campus_python

    Initialization timing:
    - Can be instantiated BEFORE Flask apps are created
    - Apps can be created later via create_app()
    - Apps must be registered via register_test_app() before requests are made
    - App lookup happens at request time, not initialization time

    Usage:
        # Create test client (apps don't need to exist yet)
        test_client = TestCampusRequest(base_url="https://campus.test")

        # Create Flask apps
        auth_app = create_app(campus.auth)
        api_app = create_app(campus.api)

        # Register apps for routing
        register_test_app("https://campus.test", auth_app, path_prefix="/auth")
        register_test_app("https://campus.test", api_app, path_prefix="/api")

        # Use test client
        test_client.get("/auth/v1/root/")  # Routes to auth_app
        test_client.get("/api/v1/circles/")  # Routes to api_app
    """

    def __init__(
            self,
            base_url: str | None = None,
            *,
            auth: Any = None,  # For compatibility with JsonClient ABC (ignored)
            headers: Any = None,  # For compatibility with JsonClient ABC (ignored)
            timeout: int = 10,
            **kwargs: Any
    ):
        """Initialize test client.

        Args:
            base_url: Base URL for determining which app to use
            auth: Authentication (ignored, for JsonClient ABC compatibility)
            headers: Default headers (ignored, for JsonClient ABC compatibility)
            timeout: Request timeout in seconds (for compatibility)
            **kwargs: Additional arguments (for compatibility)
        """
        self.base_url = base_url or ""
        self._timeout = timeout

        # Override headers for set_bearer_authorization/set_basic_authorization
        self._override_auth_headers: dict[str, str] | None = None

        # Note: We do NOT look up app at initialization time!
        # Apps can be registered later via register_test_app()

    def _get_app_for_request(self, path: str) -> flask.Flask:
        """Get the Flask app for a specific request path.

        Uses the test app registry to route to the correct app based on
        base_url and path prefix.

        Args:
            path: The request path

        Returns:
            The Flask app to handle this request

        Raises:
            ValueError: If no app is registered for this base_url and path
        """
        app = get_test_app(self.base_url, path)
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
        # Return override headers if set, otherwise load from environment
        if self._override_auth_headers is not None:
            return campus.model.HttpHeader(**self._override_auth_headers)
        return self._load_auth_headers()

    def _load_auth_headers(self) -> campus.model.HttpHeader:
        """Load authentication headers from environment variables.

        Returns:
            HttpHeader with authentication credentials
        """
        from campus.common import env

        # Try ACCESS_TOKEN first (Bearer auth)
        access_token = env.get("ACCESS_TOKEN")
        if access_token:
            return campus.model.HttpHeader.from_bearer_token(access_token)

        # Try CLIENT_ID and CLIENT_SECRET (Basic auth)
        client_id = env.get("CLIENT_ID")
        client_secret = env.get("CLIENT_SECRET")
        if client_id and client_secret:
            return campus.model.HttpHeader.from_credentials(client_id, client_secret)

        # Return empty headers for unauthenticated requests
        return campus.model.HttpHeader()

    def reset_authorization(self) -> None:
        """Reset authorization back to client credentials from environment.

        This matches CampusRequest behavior - it resets to using the
        CLIENT_ID and CLIENT_SECRET from environment variables.

        After calling this, headers will be loaded dynamically from env,
        allowing tests to change credentials between test classes.
        """
        self._override_auth_headers = None  # Clear override, use env vars

    def set_basic_authorization(self, client_id: str, secret: str) -> None:
        """Set Basic Authorization header.

        Args:
            client_id: Client ID for basic auth
            secret: Client secret for basic auth
        """
        self._override_auth_headers = campus.model.HttpHeader.from_credentials(
            client_id, secret
        )

    def set_bearer_authorization(self, token: str) -> None:
        """Set Bearer Authorization header.

        Args:
            token: Bearer token
        """
        self._override_auth_headers = campus.model.HttpHeader.from_bearer_token(
            token
        )

    def _get_auth_headers_dict(self) -> dict[str, str]:
        """Get authentication headers as dict for requests.

        Returns:
            Dictionary of HTTP headers for authentication
        """
        if self._override_auth_headers is not None:
            return dict(self._override_auth_headers)
        return dict(self._load_auth_headers())

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
            headers=self._get_auth_headers_dict()
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
            headers=self._get_auth_headers_dict()
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
            headers=self._get_auth_headers_dict()
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
            headers=self._get_auth_headers_dict()
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
            headers=self._get_auth_headers_dict()
        )
        return FlaskTestResponse(response)


def patch_campus_python() -> None:
    """Patch campus_python to use TestCampusRequest in tests.

    This function monkey-patches campus_python.json_client.CampusRequest
    with TestCampusRequest, allowing all Campus client code to use
    Flask test clients for testing without actual HTTP calls.

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
