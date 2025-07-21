"""client.base

Base client functionality for Campus services.

Provides common authentication, HTTP handling, and utility methods
that are shared across all service clients.
"""

import os
import json
import requests
from typing import Optional, Dict, Any, Union
from urllib.parse import urljoin

from .errors import (
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)
from . import config


class BaseClient:
    """Base class for all Campus service clients.

    Provides common functionality including authentication, HTTP request handling,
    and error management that is shared across all service-specific clients.
    """

    def __init__(self, base_url: Optional[str] = None):
        """Initialize base client.

        Args:
            base_url: Override default base URL for the service
        """
        self.base_url = base_url or self._get_default_base_url()
        self._client_id: Optional[str] = None
        self._client_secret: Optional[str] = None
        self._access_token: Optional[str] = None

        # Try to load credentials from environment
        self._load_credentials_from_env()

    def _get_default_base_url(self) -> str:
        """Get the default base URL for this service.

        Subclasses should override this to specify their service name,
        or clients can pass base_url explicitly to the constructor.

        Returns:
            str: The default base URL for the service
        """
        # Default to vault URL for backward compatibility
        # Subclasses should override this method
        return config.get_vault_base_url()

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
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

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
        headers = self._get_headers()

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30
            )

            # Handle HTTP status codes
            if response.status_code == 401:
                raise AuthenticationError("Authentication failed")
            elif response.status_code == 403:
                raise AccessDeniedError("Access denied")
            elif response.status_code == 404:
                raise NotFoundError("Resource not found")
            elif response.status_code == 400:
                error_msg = "Validation error"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg = error_data["error"]
                except:
                    pass
                raise ValidationError(error_msg)
            elif not response.ok:
                raise NetworkError(
                    f"HTTP {response.status_code}: {response.text}")

            # Parse JSON response
            try:
                return response.json()
            except json.JSONDecodeError:
                # Some endpoints might return empty responses
                return {}

        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request.

        Args:
            path: API path to request
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("GET", path, params=params)

    def _post(self, path: str, data: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            path: API path to request
            data: Request body data
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("POST", path, data=data, params=params)

    def _put(self, path: str, data: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a PUT request.

        Args:
            path: API path to request
            data: Request body data
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("PUT", path, data=data, params=params)

    def _delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a DELETE request.

        Args:
            path: API path to request
            params: Optional query parameters

        Returns:
            Dict[str, Any]: Parsed JSON response
        """
        return self._make_request("DELETE", path, params=params)
