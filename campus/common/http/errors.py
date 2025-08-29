"""campus.common.http.errors

Common error types raised from requests.
"""

# pylint: disable=unnecessary-ellipsis


class HttpError(Exception):
    """Base exception for all request-response errors."""
    ...


class RequestError(HttpError):
    """Base exception for all request errors."""
    ...


class ResponseError(HttpError):
    """Base exception for all response errors."""
    ...


class AuthenticationError(RequestError):
    """Raised when authentication fails."""
    ...


class NetworkError(RequestError):
    """Raised when network communication fails."""
    ...


class MalformedResponseError(ResponseError):
    """Raised when the API response is malformed."""
    ...
