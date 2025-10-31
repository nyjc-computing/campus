"""campus.common.validation.flask

Common utility functions for validation of flask requests and responses.
"""

import typing
import inspect
from functools import wraps
from json import JSONDecodeError
from typing import (
    Any,
    Callable,
    Generic,
    Mapping,
    NoReturn,
    Protocol,
    Type,
    TypeVar
)

import flask
from werkzeug import Response as FlaskResponse

from campus.common.errors import api_errors
from campus.common.validation import record

R = TypeVar("R", covariant=True)
# Only expecting strings or dicts
JsonObject = dict[str, Any]
StatusCode = int
ViewFunctionDecorator = Callable[["ViewFunction"], "ViewFunction"]
# Actually, view functions may return a variety of return values which Flask is
# able to handle
# But Campus API sticks to JSON-serializable return values, with a status code
JsonResponse = tuple[dict[str, Any], StatusCode]
HtmlResponse = tuple[str, StatusCode]


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


def get_user_agent() -> str:
    """Get the User-Agent from the Flask request."""
    if not flask.has_request_context():
        raise RuntimeError("No Flask request context available")
    return flask.request.headers.get("User-Agent", "Unknown")


def get_request_payload() -> dict[str, typing.Any]:
    """Get the JSON payload from the Flask request."""
    if not flask.has_request_context():
        raise RuntimeError("No Flask request context available")
    if flask.request.method == "GET":
        return dict(flask.request.args)

    json_payload = flask.request.get_json(silent=True)
    if json_payload is None:
        raise api_errors.InvalidRequestError(
            message="Malformed JSON payload",
            error_code="MALFORMED_REQUEST",
            body=flask.request.data,
        )
    if not isinstance(json_payload, dict):
        raise api_errors.InvalidRequestError(
            message="Expected object in JSON payload",
            body=json_payload,
        )
    return json_payload


def has_default(parameter: inspect.Parameter) -> bool:
    """Check if a function parameter has a default value."""
    return parameter.default is not inspect.Parameter.empty


def is_keyword_supported(parameter: inspect.Parameter) -> bool:
    """Check if a parameter can be passed as a keyword argument."""
    return parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )


def is_optional(parameter: inspect.Parameter) -> bool:
    """Check if a parameter is Optional.

    A parameter is optional if:
    - Its annotation is of the form Optional[T] or Union[T, None]
    - It has a default value
    """
    origin = typing.get_origin(parameter.annotation)
    if not origin is typing.Union:
        return False
    args = typing.get_args(parameter.annotation)
    if not type(None) in args:
        return False
    if not has_default(parameter):
        return False
    return True


def reconcile(
        request_args: dict[str, typing.Any],
        func: Callable[..., typing.Any],
        allow_extra: bool = False,
) -> tuple[dict[str, typing.Any], dict[str, typing.Any], list[str]]:
    """Reconcile request arguments with function parameters. Returns a tuple of:
    - reconciled arguments (with defaults applied)
    - extra arguments (not in function parameters)
    - missing required parameters

    Args:
        request_args: The arguments from the request (e.g., URL params)
        params: The function parameters to reconcile against
        allow_extra: Whether to allow extra arguments not in params
                     if True, they are included in reconciled args
                     if False, they are returned in extra_args
    """
    func_params = dict(inspect.signature(func).parameters)
    MISSING: object = object()
    reconciled: dict[str, typing.Any] = {}
    extra_args: dict[str, typing.Any] = {}
    missing_params: list[str] = []
    for name, param in func_params.items():
        arg = request_args.get(name, MISSING)
        if not is_optional(param) and arg is MISSING:
            missing_params.append(name)
        else:
            reconciled[name] = param.default if arg is MISSING else arg
    extra_args = {k: v for k, v in request_args.items()
                  if k not in func_params}
    if allow_extra:
        reconciled.update(extra_args)
        extra_args = {}
    return reconciled, extra_args, missing_params


def unpack_into(
        func: typing.Callable[..., typing.Any],
        **request_args: typing.Any,
) -> typing.Any:
    """Unpack request arguments into the given function's arguments,
    based on its signature.
    """
    reconciled, extra_args, missing_params = reconcile(request_args, func)
    if missing_params:
        raise KeyError(f"Missing required parameters: {missing_params}")
    # Call the original function with unpacked arguments
    return func(**reconciled, **extra_args)


def unpack_request(
        func: typing.Callable[..., typing.Any]
) -> typing.Callable[[], typing.Any]:
    """Decorator that unpacks Flask request into the decorated function's
    arguments, based on its signature.

    GET requests will use URL parameters, POST/PUT requests will use JSON body.
    """
    # Validate func annotations
    if not func.__annotations__:
        raise ValueError(f"{func.__name__} missing type annotations")
    for param in inspect.signature(func).parameters.values():
        if not is_keyword_supported(param):
            raise ValueError(
                f"Parameter {param.name!r} must be keyword-argument-compatible"
            )

    @wraps(func)
    def wrapper() -> typing.Any:
        request_args = get_request_payload()
        return unpack_into(func, **request_args)

    return wrapper


def validate_request_and_extract_json(
        schema: Mapping[str, Type], *,
        on_error: ErrorHandler,
) -> JsonObject:
    """Validate the request JSON body against the provided schema before
    returning the payload.
    """
    try:
        payload = get_request_payload()
        record.validate_keys(
            payload,
            schema,
        )
    except (KeyError, TypeError, JSONDecodeError) as err:
        on_error(400, message=err.args[0])
    else:
        return payload


def validate_request_and_extract_urlparams(
        schema: Mapping[str, Type], *,
        on_error: ErrorHandler,
        ignore_extra: bool = False,
        strict: bool = False,
) -> JsonObject:
    """Validate the request URL parameters against the provided schema before
    returning the parameters.
    """
    try:
        params = get_request_payload()
        record.validate_keys(
            params,
            schema,
            ignore_extra=ignore_extra,
            required=strict  # If strict, all schema keys are required
        )
    except (KeyError, TypeError) as err:
        on_error(400, message=err.args[0])
    else:
        return params


def validate_json_response(
        schema: Mapping[str, Type],
        resp_json: Mapping[str, Any], *,
        on_error: ErrorHandler,
        ignore_extra: bool = True,
        error_status_code: StatusCode = 500,
        error_message: str | None = None,
) -> None:
    """Validate the response JSON body against the provided schema."""
    if resp_json is None:
        on_error(500, message="Response body must be a JSON object")
        return
    try:
        record.validate_keys(resp_json, schema, ignore_extra=ignore_extra)
    except (KeyError, TypeError) as err:
        on_error(error_status_code, message=error_message or err.args[0])
