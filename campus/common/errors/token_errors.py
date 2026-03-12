"""campus.common.errors.token_errors

Token error definitions for Campus.
These errors represent all possible JSON errors from the /token endpoint.
"""

__all__ = [
    "AccessDeniedError",
    "AuthorizationPendingError",
    "ExpiredTokenError",
    "InvalidClientError",
    "InvalidGrantError",
    "InvalidRequestError",
    "InvalidScopeError",
    "SlowDownError",
    "TOKEN_RESPONSE_ERROR_TYPES",
    "TokenError",
    "UnauthorizedClientError",
    "UnsupportedGrantTypeError",
]

from typing import NoReturn

from . import base
from .base import TOKEN_RESPONSE_ERROR_TYPES


def raise_from_error(
        error: base.TokenResponseErrorType,
        error_description: str,
        error_uri: str | None = None,
        **details
) -> NoReturn:
    match error:
        case "invalid_client":
            errorClass = InvalidClientError
        case "invalid_grant":
            errorClass = InvalidGrantError
        case "invalid_request":
            errorClass = InvalidRequestError
        case "invalid_scope":
            errorClass = InvalidScopeError
        case "unauthorized_client":
            errorClass = UnauthorizedClientError
        case "unsupported_grant_type":
            errorClass = UnsupportedGrantTypeError
        # Device Authorization Flow errors (RFC 8628)
        case "authorization_pending":
            errorClass = AuthorizationPendingError
        case "slow_down":
            errorClass = SlowDownError
        case "expired_token":
            errorClass = ExpiredTokenError
        case "access_denied":
            errorClass = AccessDeniedError
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


class TokenError(base.OAuthError):
    """OAuth2 Token Errors
    
    From RFC 6749 Section 5.2
    https://datatracker.ietf.org/doc/html/rfc6749#section-5.2
    """
    error: base.TokenResponseErrorType  # type: ignore
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, **details)


class InvalidClientError(TokenError):
    """Invalid Client error.

    Client authentication failed (e.g. unknown client, no client
    authentication included, or unsupported authentication method).
    The authorization server MAY return an HTTP 401 (Unauthorized)
    status code to indicate which HTTP authentication schemes are
    supported.
    If the client attempted to authenticate via the "Authorization"
    request header field, the authorization server MUST respond with
    an HTTP 401 (Unauthorized) status code and include the
    "WWW-Authenticate" response header field matching the
    authentication scheme used by the client.
    """
    status_code: int = 401
    error = "invalid_client"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class InvalidGrantError(TokenError):
    """Invalid Grant error.

    The provided authorization grant (e.g. authorization code,
    resource owner credentials) or refresh token is invalid,
    expired, revoked, does not match the redirection URI used
    in the authorization request, or was issued to another client.
    """
    status_code: int = 400
    error = "invalid_grant"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class InvalidRequestError(TokenError):
    """Invalid Request error.

    The request is missing a required parameter, includes an unsupported
    parameter value (other than grant type), repeats a parameter,
    includes multiple credentials, utilizes more than one mechanism for
    authenticating the client, or is otherwise malformed.
    """
    status_code: int = 400
    error = "invalid_request"
    error_uri = None

    def __init__(self, error_description: str = "", **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class InvalidScopeError(TokenError):
    """Invalid Scope error.

    The requested scope is invalid, unknown, malformed, or exceeds
    the scope granted by the resource owner.
    """
    status_code: int = 400
    error = "invalid_scope"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class UnauthorizedClientError(TokenError):
    """Unauthorized Client error.

    The authenticated client is not authorized to use this
    authorization grant type.
    """
    status_code: int = 400
    error = "unauthorized_client"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, error_uri=None, **details)

class UnsupportedGrantTypeError(TokenError):
    """Unsupported Grant Type error.

    The authorization grant type is not supported by the
    authorization server.
    """
    status_code: int = 400
    error = "unsupported_grant_type"
    error_uri = None

    def __init__(self, error_description: str, **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


# Device Authorization Flow errors (RFC 8628)
# https://datatracker.ietf.org/doc/html/rfc8628#section-3.5


class AuthorizationPendingError(TokenError):
    """Authorization Pending error.

    The authorization request is still pending; the client should
    continue to poll the token endpoint.

    From RFC 8628 Section 3.5
    """
    status_code: int = 400
    error = "authorization_pending"
    error_uri = None

    def __init__(self, error_description: str = "", **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class SlowDownError(TokenError):
    """Slow Down error.

    The client is polling too frequently and should reduce the
    frequency of its polls.

    From RFC 8628 Section 3.5
    """
    status_code: int = 400
    error = "slow_down"
    error_uri = None

    def __init__(self, error_description: str = "", **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class ExpiredTokenError(TokenError):
    """Expired Token error.

    The "device_code" has expired and the client must restart the
    device authorization flow.

    From RFC 8628 Section 3.5
    """
    status_code: int = 400
    error = "expired_token"
    error_uri = None

    def __init__(self, error_description: str = "", **details) -> None:
        super().__init__(error_description, error_uri=None, **details)


class AccessDeniedError(TokenError):
    """Access Denied error.

    The resource owner or authorization server denied the access request.

    From RFC 8628 Section 3.5
    """
    status_code: int = 400
    error = "access_denied"
    error_uri = None

    def __init__(self, error_description: str = "", **details) -> None:
        super().__init__(error_description, error_uri=None, **details)
