"""common.validation.flask

Common utility functions for validation of flask requests and responses.
"""

from functools import wraps
from json import JSONDecodeError
from typing import Any, Callable, Generic, Mapping, NoReturn, Protocol, Type, TypeVar

from flask import has_request_context, request as flask_request
from werkzeug.wrappers import Response as FlaskResponse

from common.validation import record

R = TypeVar("R", covariant=True)
# Only expecting strings or dicts
JsonObject = dict[str, Any]
StatusCode = int
ViewFunctionDecorator = Callable[["ViewFunction"], "ViewFunction"]
# Actually, view functions may return a variety of return values which Flask is
# able to handle
# But Campus API sticks to JSON-serializable return values, with a status code
JsonResponse = tuple[dict[str, Any], StatusCode]


class ErrorHandler(Protocol):
    """Define an ErrorHandler as a function that takes a status code and
    optional keyword arguments.

    Error Handlers must raise an exception.
    """
    def __call__(self, status: StatusCode, **body) -> NoReturn:
        """An error handler returns None"""
        ...


class ViewFunction(Protocol, Generic[R]):
    """A view function that takes arbitrary arguments and returns a response.
    """
    def __call__(self, *args: str, **kwargs) -> R:
        ...


JsonViewFunction = ViewFunction[JsonResponse]
FlaskViewFunction = ViewFunction[FlaskResponse]


def unpack_request_urlparams(vf: ViewFunction[R]) -> ViewFunction[R]:
    """Unpacks the request URL parameters into the view function."""
    @wraps(vf)
    def unpackedvf(*args: str, **kwargs) -> R:
        """The decorated ViewFunction that unpacks the request URL parameters
        into the inner view-function.
        """
        # Unpack URL parameters into kwargs
        kwargs.update(flask_request.view_args or {})
        return vf(*args, **kwargs)
    return unpackedvf


def unpack_request_json(vf: ViewFunction) -> ViewFunction:
    """Unpacks the request JSON body into the view function."""
    @wraps(vf)
    def unpackedvf(*args: str, **kwargs) -> JsonResponse:
        """The decorated ViewFunction that unpacks the request JSON body into
        the inner view-function.
        """
        if not has_request_context():
            raise RuntimeError("Request context not available")

        payload = flask_request.get_json(silent=True)
        if payload is None:
            raise JSONDecodeError("Invalid JSON", "", 0)

        return vf(*args, **kwargs, **payload)
    return unpackedvf


def validate(
        *,
        request: Mapping[str, Type] | None = None,
        response: Mapping[str, Type] | None = None,
        on_error: ErrorHandler,
) -> ViewFunctionDecorator:
    """Returns a decorator that takes a view-function and returns a
    validated-view-function.

    The validated-view-function only takes positional arguments, passing them
    to the wrapped view-function.
    The validated-view-function will unpack the request JSON body and pass it
    to the wrapped view-function as keyword arguments.

    An error handler must be provided, which will be called with the status
    code and any additional keyword arguments.
    The error handler must raise an exception.
    """

    def vfdecorator(vf: ViewFunction) -> ViewFunction:
        """Validates the current Flask request JSON body, and unpacks it into
        the wrapped view-function.
        Validates the response JSON body before returning.
        """
        # TODO: provide helpful validation hints
        @wraps(vf)
        def validatedvf(*args: str, **payload) -> JsonResponse:
            """The decorated ValidatedViewFunction that unpacks the response
            JSON body into the inner view-function.
            """
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
            # Call view function
            resp_json, status_code = vf(*args, **payload)
            assert isinstance(resp_json, dict), "Response body must be a JSON object"
            # Validate response body
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
