import inspect
from functools import wraps
from json import JSONDecodeError
from typing import (
    Any,
    Callable,
    Mapping,
    Type,
)

import flask

import campus.model
from campus.common.errors import api_errors, ValidationError, FieldError
from campus.common.validation import record

from . import parameter, types


def get_user_agent() -> str:
    """Get the User-Agent from the Flask request."""
    if not flask.has_request_context():
        raise (
            RuntimeError("No Flask request context available")
        ) from None
    return flask.request.headers.get("User-Agent", "Unknown")


def get_request_headers() -> campus.model.HttpHeader:
    """Get the headers from the Flask request as a dictionary."""
    if not flask.has_request_context():
        raise (
            RuntimeError("No Flask request context available")
        ) from None

    headers_items = list(flask.request.headers.items())
    result = campus.model.HttpHeader(headers_items)
    return result


def get_request_payload() -> dict[str, Any]:
    """Get the JSON payload from the Flask request."""
    if not flask.has_request_context():
        raise (
            RuntimeError("No Flask request context available")
        ) from None
    if flask.request.method == "GET":
        return dict(flask.request.args)

    # Bodyless requests (no Content-Type, empty body) are common for
    # DELETE calls from API clients (campus_python/campus-cli send
    # DELETE without a body), so treat them as an empty payload.
    if not flask.request.get_data(cache=True):
        return {}

    json_payload = flask.request.get_json(silent=True)
    if json_payload is None:
        raise api_errors.InvalidRequestError(
            message="Malformed JSON payload",
            error_code="MALFORMED_REQUEST",
            # Error details must stay JSON-serializable; the raw body is bytes
            body=flask.request.data.decode("utf-8", errors="replace"),
        ) from None
    if not isinstance(json_payload, dict):
        raise api_errors.InvalidRequestError(
            message="Expected object in JSON payload",
            body=json_payload,
        ) from None
    return json_payload


_BOOL_LITERALS: dict[str, bool] = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
}


def _coerce_str_value(value: Any, annotation: Any) -> Any:
    """Coerce a string request value to the annotated scalar type.

    Query and path parameters always arrive as strings, so handlers
    annotating them as int/float/bool would otherwise receive strings.
    Non-string values and other annotations pass through unchanged.

    Raises ValueError if the string is not a valid literal for the type.
    """
    if not isinstance(value, str):
        return value
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is bool:
        try:
            return _BOOL_LITERALS[value.strip().lower()]
        except KeyError:
            raise ValueError(f"invalid boolean: {value!r}") from None
    return value


def unpack_into(
        func: Callable[..., Any],
        **request_args: Any,
) -> Any:
    """Unpack request arguments into the given function's arguments,
    based on its signature.

    String values (query/path parameters) are coerced to the annotated
    int/float/bool type; a failed coercion is reported as a field error.

    Raises ValidationError with structured field errors for any issues.
    """
    reconciled, extra_args, missing_params = parameter.reconcile(
        request_args,
        func
    )

    field_errors: list[FieldError] = []

    # Check if function accepts **kwargs
    func_params = inspect.signature(func).parameters
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in func_params.values()
    )

    # Only raise error for extra arguments if function doesn't have **kwargs
    if extra_args and not has_var_keyword:
        field_errors.extend([
            FieldError(
                field=param,
                code="UNRECOGNIZED_FIELD",
                message=f"Unexpected field: {param}"
            )
            for param in extra_args
        ])

    if missing_params:
        field_errors.extend([
            FieldError(
                field=param,
                code="MISSING",
                message=f"Missing required field: {param}"
            )
            for param in missing_params
        ])

    for name, value in reconciled.items():
        param = func_params.get(name)
        if param is None or parameter.is_variadic(param):
            continue
        try:
            reconciled[name] = _coerce_str_value(value, param.annotation)
        except ValueError:
            field_errors.append(FieldError(
                field=name,
                code="INVALID_TYPE",
                message=f"Expected {param.annotation.__name__} for field: {name}"
            ))

    if field_errors:
        raise ValidationError(
            message="One or more fields are invalid",
            errors=field_errors
        )

    # Call the original function with unpacked arguments
    # Include extra_args only if function has **kwargs
    return func(**reconciled, **extra_args)


def unpack_request(
        func: Callable[..., Any]
) -> Callable[[], Any]:
    """Decorator that unpacks Flask request into the decorated function's
    arguments, based on its signature.

    GET requests will use URL parameters, POST/PUT requests will use JSON body.
    """
    # Validate func annotations
    if not func.__annotations__:
        raise (
            ValueError(f"Function {func.__name__} missing type annotations")
        ) from None
    incompatible_params = [
        param for param in inspect.signature(func).parameters.values()
        if not parameter.is_keyword_supported(param)
    ]
    if incompatible_params:
        raise ValueError(
            f"Parameters {incompatible_params} must be "
            "keyword-argument-compatible"
        ) from None

    @wraps(func)
    def wrappervf(*args, **kwargs) -> Any:
        """The view function presented to Flask"""
        assert not args, f"Positional arguments not supported: {args}"
        request_args = get_request_payload()
        return unpack_into(func, **kwargs, **request_args)

    return wrappervf


def validate_request_and_extract_json(
        schema: Mapping[str, Type], *,
        on_error: types.ErrorHandler,
) -> types.JsonObject:
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
        on_error: types.ErrorHandler,
        ignore_extra: bool = False,
        strict: bool = False,
) -> types.JsonObject:
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
        on_error: types.ErrorHandler,
        ignore_extra: bool = True,
        error_status_code: types.StatusCode = 500,
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
