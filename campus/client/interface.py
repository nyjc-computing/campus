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
    # pylint: disable=unnecessary-ellipsis

    def __init__(self, response: Any):
        self._response = response  # type: ignore

    @property
    def status(self) -> int:
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

    def json(self) -> Any:
        """Returns the response body as JSON."""
        ...


@runtime_checkable
class JsonClient(Protocol):
    """This class describes the public interface required from Client classes,
    which are used to send JSON requests.
    """
    # pylint: disable=unnecessary-ellipsis
    base_url: str

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
