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
class HttpResponse(Protocol):

    @property
    def status(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


@runtime_checkable
class HttpClient(Protocol):

    def get(self, path: str, headers: Header | None = None) -> HttpResponse: ...

    def post(self, path: str, json: Any = None, headers: Header | None = None) -> HttpResponse: ...
