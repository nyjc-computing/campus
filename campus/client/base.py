"""campus.client.base

HTTP client functionality for Campus services.

Provides common authentication, HTTP handling, and utility methods
that are shared across all service clients using composition pattern.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import requests

from campus.common.utils import secret
from campus.client.errors import (
    AuthenticationError,
    AccessDeniedError,
    ConflictError,
    NotFoundError,
    ValidationError,
    NetworkError,
    MalformedResponseError,
)

# Set up logger for this module
logger = logging.getLogger(__name__)


class HttpClient:
    """HTTP client for Campus service communication.

    Provides common functionality including authentication, HTTP request
    handling, and error management. Used via composition by service-specific
    clients.
    """

    def __init__(
            self,
            base_url: str,
            *,
            auth_scheme: str = "basic"
    ):
        """Initialize base client.

        Args:
            base_url: Override default base URL for the service
            auth_scheme: 'basic' or 'bearer' (default: 'basic')
        """
        self.base_url = base_url
        self._client_id: Optional[str] = None
        self._client_secret: Optional[str] = None
        self._access_token: Optional[str] = None
        self.auth_scheme = auth_scheme

        # Try to load credentials from environment
        self._load_credentials_from_env()

        # Prepare a persistent session and initialize headers
        self.session = requests.Session()
        try:
            self.session.headers.update(self._get_headers())
        except AuthenticationError:
            # Headers may not be available if credentials are not set yet
            pass

    def _load_credentials_from_env(self) -> None:
        """Load client credentials from environment variables.

        Attempts to load CLIENT_ID and CLIENT_SECRET from environment variables.
        """
        self._client_id = os.getenv("CLIENT_ID")
        self._client_secret = os.getenv("CLIENT_SECRET")

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set client credentials explicitly.

        Args:
            client_id: The client ID for authentication
            client_secret: The client secret for authentication
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = None  # Clear any cached token
        # Update session headers with new credentials
        self.session.headers.update(self._get_headers())

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated.

        Raises:
            AuthenticationError: If no credentials are available
        """
        if not self._client_id or not self._client_secret:
            raise AuthenticationError(
                "No credentials available. Set CLIENT_ID and CLIENT_SECRET "
                "environment variables or call set_credentials()"
            )

        # In a real implementation, this would obtain an access token
        # For now, we'll simulate having authentication
        if not self._access_token:
            self._access_token = f"token_for_{self._client_id}"

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests.

        Returns:
            Dict[str, str]: Headers including authorization and content type
        """
        self._ensure_authenticated()
        if self.auth_scheme == "basic":
            if not self._client_id or not self._client_secret:
                raise AuthenticationError(
                    "Client ID and secret must be set for Basic auth"
                )
            return {
                "Authorization": secret.encode_http_basic_auth(
                    self._client_id,
                    self._client_secret
                ),
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        elif self.auth_scheme == "bearer":
            return {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        else:
            raise ValueError("Unknown authentication scheme")

    def _make_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the service.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (will be joined with base_url)
            data: Request body data (for POST/PUT)
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            AuthenticationError: If authentication fails
            AccessDeniedError: If access is denied
            NotFoundError: If resource is not found
            ValidationError: If request validation fails
            NetworkError: If network request fails
        """
        url = urljoin(self.base_url, path.lstrip('/'))
        # Always update session headers before request in case credentials changed
        self.session.headers.update(self._get_headers())

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=30
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e
        else:
            # Log response details for debugging
            logger.debug(
                f"Response received: {method} {url} -> "
                f"Status: {response.status_code}, "
                f"Content-Type: {response.headers.get('content-type', 'unknown')}"
            )

            # Helper function to safely parse JSON responses
            def safe_json_parse(response):
                try:
                    return response.json()
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(
                        f"Failed to parse JSON response: Status {response.status_code}, "
                        f"Content-Type: {response.headers.get('content-type', 'unknown')}, "
                        f"Body: {response.text[:500]}"
                    )
                    # Return a generic error message with the response details
                    return {
                        "error": "Invalid JSON response",
                        "status_code": response.status_code,
                        "content_type": response.headers.get('content-type', 'unknown'),
                        "body_preview": response.text[:200]
                    }

            breakpoint()
            match response.status_code:
                case 400:
                    raise ValidationError(safe_json_parse(response))
                case 401:
                    raise AuthenticationError(safe_json_parse(response))
                case 403:
                    raise AccessDeniedError(safe_json_parse(response))
                case 404:
                    raise NotFoundError(safe_json_parse(response))
                case 409:
                    raise ConflictError(safe_json_parse(response))
                case _:
                    if not response.ok:
                        logger.error(
                            f"HTTP error {response.status_code}: "
                            f"Content-Type: {response.headers.get('content-type', 'unknown')}, "
                            f"Body: {response.text[:500]}"
                        )
                        raise NetworkError(
                            f"HTTP {response.status_code}: {response.text}")

            # Parse JSON response
            if not response.content or response.content.strip() == b'':
                # Genuine empty response (no content)
                return {}
            try:
                return response.json()
            except json.JSONDecodeError as e:
                # Response is not valid JSON
                raise MalformedResponseError("Invalid JSON response") from e

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request.

        Args:
            path: API path to request
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("GET", path, params=params)

    def post(
            self,
            path: str,
            data: Dict[str, Any],
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            path: API path to request
            data: Request body data
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("POST", path, data=data, params=params)

    def put(
            self,
            path: str,
            data: Dict[str, Any],
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a PUT request.

        Args:
            path: API path to request
            data: Request body data
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("PUT", path, data=data, params=params)

    def patch(
            self,
            path: str,
            data: Dict[str, Any],
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a PATCH request.

        Args:
            path: API path to request
            data: Request body data
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("PATCH", path, data=data, params=params)

    def delete(
            self,
            path: str,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a DELETE request.

        Args:
            path: API path to request
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("DELETE", path, params=params)
