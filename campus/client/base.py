"""campus.client.base

HTTP client functionality for Campus services.

Provides common authentication, HTTP handling, and utility methods
that are shared across all service clients using composition pattern.
"""

import os

from typing import Any, Callable, Literal, Optional, Self, TypedDict
from urllib.parse import urljoin

import requests

from campus.common.utils import secret
from campus.client import config
from campus.client.errors import (
    AuthenticationError,
    NetworkError,
)
from campus.client.interface import JsonClient, JsonDict, JsonResponse


ClientFactory = Callable[[], JsonClient]
ClientHeader = dict[str, str]


class BasicCredentials(TypedDict):
    """Client credentials for authentication."""
    client_id: str
    client_secret: str


class BearerCredentials(TypedDict):
    """Client credentials for authentication."""
    access_token: str


def check_env_var(var_name: str) -> str:
    """Check if an environment variable is set and return its value.

    Args:
        var_name: The name of the environment variable to check.

    Raises:
        AuthenticationError: If the environment variable is not set.
    """
    value = os.getenv(var_name)
    if not value:
        raise AuthenticationError(f"Missing {var_name} environment variable")
    return value


class RequestsResponse(JsonResponse):
    """Response wrapper for requests package, to conform to JsonResponse
    interface.
    """

    def __init__(self, response: requests.Response):
        self._response = response

    @property
    def status(self) -> int:  # pylint: disable=missing-function-docstring
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:  # pylint: disable=missing-function-docstring
        # Convert to plain dict[str, str]
        return {k: v for k, v in self._response.headers.items()}

    @property
    def text(self) -> str:  # pylint: disable=missing-function-docstring
        return self._response.text

    def json(self):  # pylint: disable=missing-function-docstring
        return self._response.json()


class RequestsClient(JsonClient):
    """
    HTTP client for Campus service communication using the requests package.

    This implementation uses a persistent requests.Session for all HTTP requests,
    setting authentication and content headers once per credential change. It provides
    methods for sending HTTP requests and handling authentication automatically.
    """
    auth_scheme: Literal["basic", "bearer"]
    credentials: BasicCredentials | BearerCredentials
    headers: ClientHeader

    def __init__(
            self,
            base_url: Optional[str] = None,
            *,
            auth_scheme: Literal["basic", "bearer"] = "basic"
    ):
        """
        Initialize the RequestsClient.

        Args:
            base_url: Override default base URL for the service.
            auth_scheme: 'basic' or 'bearer' (default: 'basic').

        This sets up a persistent requests.Session and loads credentials from the environment.
        Headers are set once and reused for all requests until credentials change.
        """
        self.base_url = base_url or self._get_default_base_url()
        self.auth_scheme = auth_scheme
        self.headers = ClientHeader({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

        # Try to load credentials from environment
        self._load_credentials_from_env()
        # Prepare a persistent session and set default headers
        self._session = requests.Session()
        self._update_session_headers()

    def _update_session_headers(self):
        """
        Update the session's default headers based on the current credentials and auth scheme.
        This is called after initialization and whenever credentials are changed.
        """
        self._update_credential_headers()
        self._session.headers.clear()
        self._session.headers.update(self.headers)

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
        """
        Load client credentials from environment variables.

        Attempts to load ACCESS_TOKEN (for bearer auth) or CLIENT_ID and
        CLIENT_SECRET (for basic auth) from environment variables, depending on
        the configured authentication scheme.

        Raises:
            AuthenticationError: If required environment variables are absent.
        """
        match self.auth_scheme:
            case "basic":
                self.set_credentials(
                    client_id=check_env_var("CLIENT_ID"),
                    client_secret=check_env_var("CLIENT_SECRET")
                )
            case "bearer":
                self.set_credentials(
                    access_token=check_env_var("ACCESS_TOKEN")
                )

    def set_credentials(
        self,
        *,
        access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """
        Set client credentials explicitly and update session headers.

        Args:
            access_token: The access token for Bearer authentication.
            client_id: The client ID for authentication.
            client_secret: The client secret for authentication.

        Raises:
            ValueError: If invalid credentials are provided.
        """
        if self.auth_scheme == "bearer":
            if access_token is None:
                raise ValueError(
                    "Access token is required for Bearer authentication"
                )
            self.credentials = BearerCredentials(
                access_token=access_token
            )
        elif self.auth_scheme == "basic":
            if client_id is None or client_secret is None:
                raise ValueError(
                    "Both client_id and client_secret are required for "
                    "Basic authentication"
                )
            self.credentials = BasicCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
        self._update_session_headers()

    def _check_credentials(self) -> None:
        """Ensure the client is authenticated.

        Raises:
            AuthenticationError: If no credentials are available
        """
        if self.auth_scheme == "bearer" and self.credentials.get("access_token"):
            pass
        elif (
                self.auth_scheme == "basic" and
                self.credentials.get("client_id")
                and self.credentials.get("client_secret")
        ):
            pass
        else:
            raise AuthenticationError("Client has no credentials.")

    def _update_credential_headers(self) -> None:
        """Update headers with credentials for API requests."""
        self._check_credentials()
        match self.auth_scheme:
            case "basic":
                creds = BasicCredentials(self.credentials)  # type: ignore
                auth_str = secret.encode_http_basic_auth(
                    creds["client_id"],
                    creds["client_secret"]
                )
            case "bearer":
                creds = BearerCredentials(self.credentials)  # type: ignore
                auth_str = f"Bearer {creds['access_token']}"
            case _:
                raise ValueError("Unknown authentication scheme")
        self.headers["Authorization"] = auth_str

    def _make_request(
            self,
            method: str,
            path: str,
            params: Any = None,
            json: Any = None,
    ) -> RequestsResponse:
        """
        Make an HTTP request using the persistent session.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path (will be joined with base_url).
            json: Optional JSON body for the request.

        Returns:
            RequestsResponse: A response wrapper object.

        Raises:
            NetworkError: If the network request fails.
        """
        url = urljoin(self.base_url, path.lstrip('/'))
        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=json,
                timeout=30
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e
        else:
            return RequestsResponse(response)

    def get(self: Self, path: str, params: JsonDict | None = None) -> JsonResponse:
        return self._make_request("GET", path, params=params)

    def post(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        return self._make_request("POST", path, json=json)

    def put(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        return self._make_request("PUT", path, json=json)

    def patch(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        return self._make_request("PATCH", path, json=json)

    def delete(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        return self._make_request("DELETE", path, json=json)


class Resource:
    """Resource class that represents API resources"""
    client: JsonClient
    path: str

    def __init__(
            self,
            client_or_parent: "JsonClient | Resource",
            *parts: str
    ):
        match client_or_parent:
            case Resource():
                self.client = client_or_parent.client
                self.path = f"{client_or_parent.path}/{'/'.join(parts)}"
            case JsonClient():
                self.client = client_or_parent
                self.path = '/'.join(parts)

    def __repr__(self) -> str:
        return f"Resource(client={self.client}, path={self.path})"
    
    def __str__(self) -> str:
        return self.path

    def make_path(self, path: str) -> str:
        """Create a full path for a sub-resource or action."""
        return f"{self.path}/{path.lstrip('/')}"
