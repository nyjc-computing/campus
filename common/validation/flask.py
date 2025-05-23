"""common/validation/flask

Common utility functions for validation of flask requests and responses.
"""

from functools import wraps
from json import JSONDecodeError
from typing import Any, Callable, Mapping, Protocol, Type

from flask import Request, has_request_context, request as flask_request

from common.validation import record

# Only expecting strings or dicts
JsonObject = dict[str, Any]
StatusCode = int
# Actually, view functions may return a variety of return values which Flask is
# able to handle
# But Campus API sticks to JSON-serializable return values, with a status code
FlaskResponse = tuple[dict[str, Any], StatusCode]
ErrorHandler = Callable[[StatusCode], None]


class ViewFunction(Protocol):
    """Define a ViewFunction as a function that takes arbitrary arguments and
    returns what a Flask view function would return (for now, just a tuple
    [JsonObject, StatusCode]
    """

    def __call__(self, *args: str, **kwargs) -> FlaskResponse:
        """A view function returns a Flask response"""
        ...


class ValidatedViewFunction(Protocol):
    """A view function that validates the incoming JSON request body before
    unpacking its contents into an inner view function.
    """

    def __call__(self, *args: str) -> FlaskResponse:
        """A validated view function takes no keyword arguments, only
        positional arguments.
        Positional arguments are expected to come from the request path, e.g.
        resource ids.
        Keyword arguments will come from the request JSON body.
        """


def unpack_request(vf: ViewFunction) -> ViewFunction:
    """Unpacks the request JSON body into the view function.

    This is a helper function to be used in the decorator.
    """
    def vfdecorator(*args: str, **kwargs) -> FlaskResponse:
        """The decorated ViewFunction that unpacks the request JSON body into
        the inner view-function.
        """
        if not has_request_context():
            raise RuntimeError("Request context not available")

        payload = flask_request.get_json(silent=True)
        if payload is None:
            raise JSONDecodeError("Invalid JSON", "", 0)

        return vf(*args, **kwargs, **payload)
    return vfdecorator


def validate_and_unpack(
        *,
        request: Mapping[str, Type] | None = None,
        response: Mapping[str, Type] | None = None,
        on_error: ErrorHandler = lambda s: None,
) -> Callable[[ViewFunction], ValidatedViewFunction]:
    """Returns a decorator that takes a view-function and returns a
    validated-view-function.

    The validated-view-function only takes positional arguments, passing them
    to the wrapped view-function.
    The validated-view-function will unpack the request JSON body and pass it
    to the wrapped view-function as keyword arguments.
    """

    def vfdecorator(vf: ViewFunction) -> ValidatedViewFunction:
        """Validates the current Flask request JSON body, and unpacks it into
        the wrapped view-function.
        Validates the 
        """
        # TODO: provide helpful validation hints
        payload = unpack_json(flask_request, on_error)
        # Validate request body
        if request is not None:
            try:
                record.validate_keys(
                    payload,
                    request,
                    ignore_extra=True,
                    required=True,
                )
            except (KeyError, TypeError):
                on_error(400)
            except Exception:
                on_error(500)

        @wraps(vf)
        def validatedvf(*args: str) -> FlaskResponse:
            """The decorated ValidatedViewFunction that unpacks the response JSON body into the inner view-function."""
            resp_json, status_code = vf(*args, **payload)
            assert isinstance(resp_json, dict), "Response body must be a JSON object"
            if response is not None and 200 <= status_code < 300:
                try:
                    record.validate_keys(
                        resp_json,
                        response,
                        ignore_extra=True,
                        required=True,
                    )
                except (KeyError, TypeError):
                    on_error(500)
                except Exception:
                    on_error(500)
            return resp_json, status_code
                

        return validatedvf
    return vfdecorator
