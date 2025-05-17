"""common/validation/flask

Common utility functions for validation of flask requests and responses.
"""

from functools import wraps
from json import JSONDecodeError
from typing import Any, Callable, Mapping, Protocol, Type

from flask import Request, request as flask_request

from common.validation import record

# Only expecting strings or dicts
JsonSerializable = str | dict[str, Any]
StatusCode = int
# Actually, view functions may return a variety of return values which Flask is
# able to handle
# But Campus API sticks to JSON-serializable return values, with a status code
FlaskResponse = tuple[JsonSerializable, StatusCode]
ErrorHandler = Callable[[StatusCode], None]


class ViewFunction(Protocol):
    """Define a ViewFunction as a function that takes arbitrary arguments and
    returns what a Flask view function would return (for now, just a tuple
    [JsonSerializable, StatusCode]
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
        ...


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
    except JSONDecodeError:
        on_error(400)
    except Exception:
        on_error(500)
    else:
        return payload
    raise AssertionError("Unreachable code")  # pragma: no cover

def validate_schema(
        *,
        request: Mapping[str, Type] | None = None,
        response: Mapping[str, Type] | None = None,
        on_error: ErrorHandler = lambda s: None,
) -> Callable[[ViewFunction], ValidatedViewFunction]:
    """Returns a decorator that takes a view-function and returns a
    validated-view-function.
    """

    def vfdecorator(vf: ViewFunction) -> ValidatedViewFunction:
        """Validates the current Flask request JSON body, and unpacks it into
        the wrapped view-function.
        Validates the 
        """
        # TODO: provide helpful validation hints
        payload = unpack_json(flask_request, on_error)
        # Validate request body
        assert isinstance(payload, dict), "Request body must be a JSON object"
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
