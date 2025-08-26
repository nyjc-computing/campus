"""campus.client.interface

Interface descriptions for the Campus client interface.

This interface is designed to:
- wrap `flask.testing.FlaskClient`
- wrap most common client interfaces e.g. `requests`
- provide a common Response interface that wraps `werkzeug.test.TestResponse, `requests.Response`, etc
- so aa to enable WSGI hooks or unit testing with a local WSGI app.
"""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

Header = Mapping[str, str]


@runtime_checkable
class BaseResponse(Protocol):
    """This class describes the public interface required from Response
    wrappers.
    """

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
class BaseClient(Protocol):
    """This class describes the public interface required from Client classes,
    which are used to send requests.
    """

    def get(self, path: str, headers: Header | None = None) -> BaseResponse:
        """Sends a GET request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def post(
            self,
            path: str,
            json: Any = None,
            headers: Header | None = None
    ) -> BaseResponse:
        """Sends a POST request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def put(
            self,
            path: str,
            json: Any = None,
            headers: Header | None = None
    ) -> BaseResponse:
        """Sends a PUT request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def delete(
            self,
            path: str,
            headers: Header | None = None
    ) -> BaseResponse:
        """Sends a DELETE request."""
        ...  # pylint: disable=unnecessary-ellipsis

    def patch(
            self,
            path: str,
            json: Any = None,
            headers: Header | None = None
    ) -> BaseResponse:
        """Sends a PATCH request."""
        ...  # pylint: disable=unnecessary-ellipsis
