"""campus.common.http.default

Default implementation for JsonClient and JsonResponse, using `requests`.
"""

from typing import Any, Callable, Iterable, Mapping, Self
from urllib.parse import urljoin

import requests

from campus.common import devops
from campus.common.utils import secret

from .errors import NetworkError
from .interface import JsonClient, JsonDict, JsonResponse

ClientFactory = Callable[[], JsonClient]
ClientHeader = dict[str, str]


class DefaultResponse(JsonResponse):
    """Default response wrapper, using `requests` package."""
    # pylint: disable=missing-function-docstring

    def __init__(self, response: requests.Response):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        # Convert to plain dict[str, str]
        return {k: v for k, v in self._response.headers.items()}

    @property
    def text(self) -> str:
        return self._response.text

    def json(self):
        return self._response.json()


class DefaultClient(JsonClient):
    """
    Default client for Campus service communication, using `requests` package.

    This implementation uses a persistent requests.Session for all requests,
    setting authentication and content headers once per credential change. It
    provides methods for sending HTTP requests and handling authentication
    automatically.
    """

    def __init__(
            self,
            base_url: str | None = None,
            *,
            auth: Iterable[str] | str | None = None,
            headers: Mapping[str, str] | None = None,
            **kwargs: Any
    ):
        """
        Initialize the RequestsClient.

        Args:
            base_url: Override default base URL for the service.
            auth_scheme: 'basic' or 'bearer' (default: 'basic').

        This sets up a persistent requests.Session and loads credentials from the environment.
        Headers are set once and reused for all requests until credentials change.
        """
        self.base_url = base_url
        assert headers is None or 'Authorization' not in headers, (
            f"'Authorization' in headers conflicts with provided auth"
        )

        # Prepare a persistent session and set default headers
        self._session = requests.Session()
        # Load credentials from environment if not provided
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
                raise ValueError("Unknown auth {auth!r}")
        self.headers["Content-Type"] = "application/json"
        self.headers["Accept"] = "application/json"

    @property
    def headers(self):
        return self._session.headers

    def _make_request(
            self,
            method: str,
            path: str,
            params: Any = None,
            json: Any = None,
    ) -> DefaultResponse:
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
        # if base_url is present, expect a partial path
        # if base_url is absent, expect a full URL
        url = (
            urljoin(self.base_url, path.lstrip('/')) if self.base_url
            else path
        )
        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=json,
                timeout=30
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from None
        else:
            return DefaultResponse(response)

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
