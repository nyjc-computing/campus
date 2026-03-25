"""campus.common.errors.auth_errors

Authorization error definitions for Campus.
These errors represent all possible HTTP error responses from the
/authorize endpoint.
"""

__all__ = [
    "AUTH_RESPONSE_ERROR_TYPES",
    "AccessDeniedError",
    "AuthorizationError",
    "InvalidRequestError",
    "InvalidScopeError",
    "ServerError",
    "TemporarilyUnavailableError",
    "UnauthorizedClientError",
    "UnsupportedResponseTypeError",
]

from typing import NoReturn

from . import base
from .base import AUTH_RESPONSE_ERROR_TYPES


def raise_from_error(
        error: base.AuthResponseErrorType,
        error_description: str = "",
        **details
) -> NoReturn:
    match error:
        case "access_denied":
            errorClass = AccessDeniedError
        case "invalid_request":
            errorClass = InvalidRequestError
        case "invalid_scope":
            errorClass = InvalidScopeError
        case "server_error":
            errorClass = ServerError
        case "temporarily_unavailable":
            errorClass = TemporarilyUnavailableError
        case "unauthorized_client":
            errorClass = UnauthorizedClientError
        case "unsupported_response_type":
            errorClass = UnsupportedResponseTypeError
        case _:
            raise ValueError(f"Unknown error type: {error}")
    raise errorClass(error_description, **details)


def raise_from_json(error_json: dict[str, str]) -> NoReturn:
    """Raise the appropriate TokenError from a JSON error response."""
    if "error" not in error_json:
        raise ValueError("No 'error' field in error response.")
    error = error_json["error"]
    error_description = error_json.get("error_description", "")
    error_uri = error_json.get("error_uri")
    if not error:
        raise ValueError("No 'error' field in error response.")
    raise_from_error(
        error=error,  # type: ignore
        error_description=error_description,
        error_uri=error_uri
    )


class AuthorizationError(base.OAuthError):
    """OAuth Authorization Errors.

    From RFC 6749 Section 4.1.2.1
    https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.2.1
    """
    error: base.AuthResponseErrorType = "invalid_request"  # type: ignore
    error_uri = None
    redirect_uri: str | None

    def __init__(
            self,
            error_description: str,
            redirect_uri: str | None = None,
            **details
    ) -> None:
        if "redirect_uri" in details:
            redirect_uri = details.pop("redirect_uri")
        super().__init__(error_description, **details)
        self.redirect_uri = redirect_uri


class AccessDeniedError(AuthorizationError):
    """Access Denied error.

    The resource owner or authorization server denied the request.
    """
    status_code: int = 400
    error = "access_denied"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, **details)


class InvalidRequestError(AuthorizationError):
    """Invalid Request error.

    The request is missing a required parameter, includes an unsupported
    parameter value (other than grant type), repeats a parameter,
    includes multiple credentials, utilizes more than one mechanism for
    authenticating the client, or is otherwise malformed.
    """
    status_code: int = 400
    error = "invalid_request"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, **details)


class InvalidScopeError(AuthorizationError):
    """Invalid Scope error.

    The requested scope is invalid, unknown, malformed, or exceeds
    the scope granted by the resource owner.
    """
    status_code: int = 400
    error = "invalid_scope"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, **details)


class ServerError(AuthorizationError):
    """Server Error.

    The authorization server encountered an unexpected
    condition that prevented it from fulfilling the request.
    (This error code is needed because a 500 Internal Server
    Error HTTP status code cannot be returned to the client
    via an HTTP redirect.)
    """
    status_code: int = 500
    error = "server_error"
    error_uri = None

    def __init__(
            self,
            error_description: str = "The authorization server encountered an unexpected error.",
            **details
    ) -> None:
        super().__init__(error_description, **details)


class TemporarilyUnavailableError(AuthorizationError):
    """Temporarily Unavailable error.

    The authorization server is currently unable to handle
    the request due to a temporary overloading or maintenance
    of the server. (This error code is needed because a 503
    Service Unavailable HTTP status code cannot be returned
    to the client via an HTTP redirect.)
    """
    status_code: int = 503
    error = "temporarily_unavailable"
    error_uri = None

    def __init__(
            self,
            error_description: str = "The authorization server is temporarily unavailable.",
            **details
    ) -> None:
        super().__init__(error_description, **details)


class UnauthorizedClientError(AuthorizationError):
    """Unauthorized Client error.

    The authenticated client is not authorized to use this
    authorization grant type.
    """
    status_code: int = 400
    error = "unauthorized_client"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, **details)


class UnsupportedResponseTypeError(AuthorizationError):
    """Unsupported Response Type error.

    The authorization server does not support obtaining
    an authorization code using this method.
    """
    status_code: int = 400
    error = "unsupported_response_type"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, **details)
