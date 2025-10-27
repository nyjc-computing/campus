from functools import wraps
import inspect
import typing

import flask


def get_request_payload() -> dict[str, typing.Any]:
    """Get the JSON payload from the Flask request."""
    if not flask.has_request_context():
        raise RuntimeError("No Flask request context available")
    if flask.request.method == "GET":
        return dict(flask.request.args)

    json_payload = flask.request.get_json(silent=True)
    if json_payload is None:
        raise ValueError("Request JSON payload is invalid or missing", flask.request.data)
    assert isinstance(json_payload, dict)
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
        params: dict[str, inspect.Parameter],
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
    MISSING: object = object()
    reconciled: dict[str, typing.Any] = {}
    extra_args: dict[str, typing.Any] = {}
    missing_params: list[str] = []
    for name, param in params.items():
        arg = request_args.get(name, MISSING)
        if not is_optional(param) and arg is MISSING:
            missing_params.append(name)
        else:
            reconciled[name] = param.default if arg is MISSING else arg
    extra_args = {k: v for k, v in request_args.items() if k not in params}
    if allow_extra:
        reconciled.update(extra_args)
        extra_args = {}
    return reconciled, extra_args, missing_params


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
        params = dict(inspect.signature(func).parameters)
        # Reconcile with function parameters
        reconciled_args, extra_args, missing_params = reconcile(
            request_args,
            params,
        )
        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")
        # Call the original function with unpacked arguments
        return func(**reconciled_args, **extra_args)

    return wrapper
