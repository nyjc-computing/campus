"""tests.flask_test.interface

This module contains schemas and interfaces for documenting Flask testing
utilities.
"""

from typing import Any, Literal, Mapping, Protocol, TypedDict, Unpack

from werkzeug.test import TestResponse



class MethodParams(TypedDict, total=False):
    """Parameters accepted by werkzeug's FlaskClient methods.

    Reference:
    - https://werkzeug.palletsprojects.com/en/stable/test/#werkzeug.test.EnvironBuilder

    Parameters not used in testing are *intentionally* commented out.
    Do not remove!
    """
    # path: str
    # base_url: str | None
    query_string: Mapping[str, str] | str | None
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    # input_stream: Any  # t.IO[bytes] | None
    # content_type: str | None
    # content_length: int | None
    # errors_stream: Any  # t.IO[str] | None
    # multithread: bool
    # multiprocess: bool
    # run_once: bool
    headers: dict[str, str] | list[tuple[str, str]] | None
    # data: bytes | str | dict[str, Any] | None
    json: dict[str, Any] | None
    # environ_base: dict[str, Any] | None
    # environ_overrides: dict[str, Any] | None
    auth: Any  # Authorization | tuple[str, str] | None
    # mimetype: str | None
    # follow_redirects: bool


class FlaskClientInterface(Protocol):
    """This interface documents the parameters accepted by werkzeug's
    test client.

    Reference:
    - https://werkzeug.palletsprojects.com/en/stable/test/#werkzeug.test.Client
    """
    # pylint: disable=missing-function-docstring

    def get(self,
            path: str = "/",
            **kwargs: Unpack[MethodParams]) -> TestResponse:
        ...

    def post(self,
             path: str = "/",
             **kwargs: Unpack[MethodParams]) -> TestResponse:
        ...

    def put(self,
            path: str = "/",
            **kwargs: Unpack[MethodParams]) -> TestResponse:
        ...

    def patch(self,
              path: str = "/",
              **kwargs: Unpack[MethodParams]) -> TestResponse:
        ...

    def delete(self,
               path: str = "/",
               **kwargs: Unpack[MethodParams]) -> TestResponse:
        ...


__all__ = [
    "MethodParams",
    "FlaskClientInterface",
]
