"""campus.common.flask.validation

This module provides utilities for validation of arguments against
parameters.
"""

import inspect
import typing


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
    """Check if a parameter is optional.

    A parameter is considered optional if it has a default value,
    or if it's a *args or **kwargs parameter."""
    return (
        has_default(parameter)
        or is_variadic(parameter)
    )

def is_variadic(parameter: inspect.Parameter) -> bool:
    """Check if a parameter is variadic (*args or **kwargs)."""
    return parameter.kind in (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    )


def reconcile(
        request_args: dict[str, typing.Any],
        func: typing.Callable[..., typing.Any],
        allow_extra: bool = False,
) -> tuple[dict[str, typing.Any], dict[str, typing.Any], list[str]]:
    """Reconcile request arguments with function parameters. Returns a
    tuple of:
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
        if is_variadic(param) and (arg != {} and arg != ()):
            reconciled[name] = arg
        elif is_optional(param):
            reconciled[name] = param.default if arg is MISSING else arg
        else:
            missing_params.append(name)
    extra_args = {k: v for k, v in request_args.items()
                  if k not in func_params}
    if allow_extra:
        reconciled.update(extra_args)
        extra_args = {}
    return reconciled, extra_args, missing_params
