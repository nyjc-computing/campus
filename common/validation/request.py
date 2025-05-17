"""common/validation/request

Common utility functions for validation of request body.
"""

from functools import wraps
from json import JsonDecodeError
from typing import Any, Mapping, Protocol, Type

from flask import Request, request

from . import record

# Only expecting strings or dicts
JsonSerializable = str | dict[str, Any]
StatusCode = int
# Actually, view functions may return a variety of return values which Flask is able to handle
# But Campus API sticks to JSON-serializable return values, with a status code
FlaskResponse = tuple[JsonSerializable, StatusCode]
ErrorHandler = Callable[[StatusCode], None]


class ViewFunction(Protocol):
    """Define a ViewFunction as a function that takes arbitrary arguments and returns what a Flask view function would return (for now, just a tuple[JsonSerializable, StatusCode]"""

    def __call__(self, *args, **kwargs) -> FlaskResponse:
        """A view function returns a Flask response"""
        pass


class ValidatedViewFunction(ViewFunction):
    """A view function that validates the incoming JSON request body before unpacking its contents into an inner view function."""

    def __call__(self, *args) -> FlaskResponse:
        """A validated view function takes no keyword arguments, only positional arguments.
        Positional arguments are expected to come from the request path, e.g. resource ids.
        Keyword arguments will come from the request JSON body.
        """
        pass


def unpack_json(request: Request, on_error: ErrorHandler) -> JsonSerializable:
    """Unpacks JSON body from the request.
    Calls the given error handler if unable to do so.
    """
    # Mimetype check
    if not request.is_json:
        on_error(415)
    # Unpack request JSON body
    try:
        payload = request.get_json()
    except JsonDecodeError:
        on_error(400)
    except Exception:
        on_error(500)
    # Validate request body
    try:
        record._validate_keys(
            payload,
            schema,
            ignore_extra=True,
            required_keys=True,
        )
    except (KeyError, TypeError):
        on_error(400)
    except Exception:
        on_error(500)
    return payload


def validate_request(schema: Mapping[str, Type], on_error: ErrorHandler = lambda: pass) -> Callable[[ViewFunction], ValidatedViewFunction]:
    """Returns a decorator that takes a view-function and returns a validated-view-function."""

    def vfdecorator(vf: ViewFunction) -> ValidatedViewFunction:
        """Validates the current Flask request JSON body, and unpacks it into the wrapped view-function."""
        # TODO: provide helpful validation hints
        payload = unpack_json(request, on_error)

        @wrapped(vf)
        def validatedvf(*args: str) -> FlaskResponse:
            """The decorated ValidatedViewFunction that unpacks the response JSON body into the inner view-function."""
            return vf(*args, **payload)

        return validatedvf
    return vfdecorator
