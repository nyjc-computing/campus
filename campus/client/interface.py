"""campus.client.interface

Interface descriptions for the Campus client interface.

This interface is designed to:
- wrap `flask.testing.FlaskClient`
- wrap most common client interfaces e.g. `requests`
- provide a common Response interface that wraps `werkzeug.test.TestResponse,
  `requests.Response`, etc
- so aa to enable WSGI hooks or unit testing with a local WSGI app.
"""

from collections.abc import Mapping
from typing import Any, Protocol, Self, runtime_checkable

Header = Mapping[str, str]
JsonDict = dict[str, Any]


@runtime_checkable
class JsonResponse(Protocol):
    """This class describes the public interface required from Response
    wrappers for JSON responses.
    """

    def __init__(self, response: Any):
        self._response = response  # type: ignore

    @property
    def status(self) -> int:
        """HTTP status code of the response."""
        ...  # pylint: disable=unnecessary-ellipsis

    @property
    def headers(self) -> dict[str, str]:
        """Returns headers of the response as a dict."""
        ...  # pylint: disable=unnecessary-ellipsis

    @property
    def text(self) -> str:
        """Returns the response body as a string."""
        ...  # pylint: disable=unnecessary-ellipsis

    def json(self) -> Any:
        """Returns the response body as JSON."""
        ...  # pylint: disable=unnecessary-ellipsis


@runtime_checkable
class JsonClient(Protocol):
    """This class describes the public interface required from Client classes,
    which are used to send JSON requests.
    """

    def get(self: Self, path: str, params: JsonDict | None = None) -> JsonResponse:
        """Sends a GET request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def post(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a POST request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def put(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a PUT request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def delete(self: Self, path: str, json: JsonDict | None = None) -> JsonResponse:
        """Sends a DELETE request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def patch(self: Self, path: str, json: Any = None) -> JsonResponse:
        """Sends a PATCH request."""
        ...  # pylint: disable=unnecessary-ellipsis
