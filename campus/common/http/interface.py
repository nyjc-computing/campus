"""campus.common.http.interface

Interface descriptions for the Campus client interface.

This interface is designed to:
- wrap `flask.testing.FlaskClient`
- wrap most common client interfaces e.g. `requests`
- provide a common Response interface that wraps `werkzeug.test.TestResponse,
  `requests.Response`, etc
- so aa to enable WSGI hooks or unit testing with a local WSGI app.
"""

from collections.abc import Mapping
from typing import Any, Iterable, Protocol, Self, runtime_checkable

from campus.common.http.errors import (
    AccessDeniedError,
    AuthenticationError,
    ConflictError,
    HttpClientError,
    NotFoundError,
    InvalidRequestError,
)

Header = Mapping[str, str]
JsonDict = dict[str, Any]


@runtime_checkable
class JsonResponse(Protocol):
    """This class describes the public interface required from Response
    wrappers for JSON responses.
    """
    # pylint: disable=unnecessary-ellipsis

    def __init__(self, response: Any):
        self._response = response  # type: ignore

    @property
    def status_code(self) -> int:
        """HTTP status code of the response."""
        ...

    @property
    def headers(self) -> dict[str, str]:
        """Returns headers of the response as a dict."""
        ...

    @property
    def text(self) -> str:
        """Returns the response body as a string."""
        ...

    def ok(self) -> bool:
        """Returns True if the response status code is 2xx, False otherwise."""
        return 200 <= self.status_code < 300

    def client_error(self) -> bool:
        """Returns True if the response status code is 4xx, False otherwise."""
        return 400 <= self.status_code < 500

    def server_error(self) -> bool:
        """Returns True if the response status code is 5xx, False otherwise."""
        return 500 <= self.status_code < 600

    def raise_for_status(self) -> None:
        """Raises an exception if the response status code indicates an error.

        Raises:
            AuthenticationError: If the status code is 401
            AccessDeniedError: If the status code is 403
            NotFoundError: If the status code is 404
            ConflictError: If the status code is 409
            InvalidRequestError: If the status code is 400 or 422
            HttpClientError: For other 4xx or 5xx status codes
        """
        if not (self.client_error() or self.server_error()):
            return

        status = self.status_code
        
        # Try to get meaningful error details from response
        try:
            # First try to parse as JSON for structured error
            response_data = self.json()
            if isinstance(response_data, dict):
                # Look for common error message fields
                error_msg = (
                    response_data.get('message') or 
                    response_data.get('error') or 
                    response_data.get('detail') or
                    response_data.get('error_description')
                )
                if error_msg:
                    message = error_msg
                else:
                    message = str(response_data)
            else:
                message = str(response_data)
        except:
            # Fall back to response text if JSON parsing fails
            try:
                message = self.text.strip() or f"HTTP {status}"
            except:
                message = f"HTTP {status} (no response body)"

        match status:
            case 400:
                raise InvalidRequestError(f"{status} Bad Request: {message}")
            case 401:
                raise AuthenticationError(f"{status} Unauthorized: {message}")
            case 403:
                raise AccessDeniedError(f"{status} Forbidden: {message}")
            case 404:
                raise NotFoundError(f"{status} Not Found: {message}")
            case 409:
                raise ConflictError(f"{status} Conflict: {message}")
            case 422:
                raise InvalidRequestError(
                    f"{status} Unprocessable Entity: {message}")
            case _:
                # Generic error for other 4xx/5xx codes
                raise HttpClientError(f"{status} HTTP Error: {message}")

    def json(self) -> Any:
        """Returns the response body as JSON."""
        ...


@runtime_checkable
class JsonClient(Protocol):
    """This class describes the public interface required from Client classes,
    which are used to send JSON requests.
    """
    base_url: str | None
    # pylint: disable=unnecessary-ellipsis

    def __init__(
            self,
            base_url: str | None = None,
            *,
            auth: Iterable[str] | str | None = None,
            headers: Mapping[str, str] | None = None,
            **kwargs: Any
    ):
        raise NotImplementedError(
            "Subclasses must override __init__()"
        )

    def get(self: Self, path: str, params: JsonDict | None = None) -> JsonResponse:
        """Sends a GET request."""
        ...

    def post(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a POST request."""
        ...

    def put(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a PUT request."""
        ...

    def delete(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a DELETE request."""
        ...

    def patch(self: Self, path: str, json: Any = None) -> JsonResponse:
        """Sends a PATCH request."""
        ...


__all__ = [
    "JsonClient",
    "JsonResponse",
]
