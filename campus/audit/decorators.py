"""campus.audit.decorators

Scope-based authorization for the campus.audit API.

Audit API keys carry a list of scopes (e.g. "traces:read",
"traces:write"); endpoints declare the scopes they require via the
@require_scopes decorator. Scopes are populated on flask.g by the
API-key authentication middleware.

Issue: #575
"""

__all__ = [
    "require_scopes",
    "scope_matches",
]

import functools
import typing

import flask

from campus.common.errors import api_errors


def scope_matches(granted: str, required: str) -> bool:
    """Check whether a granted scope satisfies a required scope.

    Wildcards on the granted scope:
    - "*" grants every scope
    - "traces:*" grants every "traces:<action>" scope (e.g.
      "traces:read", "traces:write")

    A required scope must be concrete; a wildcard in the required
    position only matches itself.

    Args:
        granted: Scope granted to the API key
        required: Scope required by the endpoint

    Returns:
        bool: True if the granted scope satisfies the requirement.
    """
    if granted == "*":
        return True
    if granted == required:
        return True
    return granted.endswith(":*") and required.startswith(granted[:-1])


def require_scopes(
        *required_scopes: str
) -> typing.Callable[[typing.Any], typing.Any]:
    """Require the authenticated API key to hold all of the given scopes.

    Reads the key's scopes from flask.g.api_key_scopes, which the
    authentication middleware populates. The request must have passed
    API-key authentication first (blueprint before_request), otherwise
    the scopes are absent and access is denied.

    Each required scope is checked against every granted scope with
    wildcard expansion (scope_matches). Requests failing the check
    raise ForbiddenError (403).

    Args:
        *required_scopes: Scopes the endpoint requires; ALL must be
            satisfied.

    Returns:
        Decorator that enforces the scope requirements.
    """
    if not required_scopes:
        raise ValueError("require_scopes() needs at least one scope")

    def decorator(func: typing.Any) -> typing.Any:
        @functools.wraps(func)
        def wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            granted_scopes = getattr(flask.g, "api_key_scopes", [])
            satisfied = all(
                any(scope_matches(granted, required) for granted in granted_scopes)
                for required in required_scopes
            )
            if not satisfied:
                raise api_errors.ForbiddenError(
                    "Missing required scope: " + ", ".join(required_scopes)
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
