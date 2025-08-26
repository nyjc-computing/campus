"""campus.client.errors

Common error types used across all campus client modules.
"""


class CampusClientError(Exception):
    """Base exception for all campus client errors."""
    ...  # pylint: disable=unnecessary-ellipsis


class AuthenticationError(CampusClientError):
    """Raised when authentication fails."""
    ...  # pylint: disable=unnecessary-ellipsis


class NetworkError(CampusClientError):
    """Raised when network communication fails."""
    ...  # pylint: disable=unnecessary-ellipsis


class MalformedResponseError(CampusClientError):
    """Raised when the API response is malformed."""
    ...  # pylint: disable=unnecessary-ellipsis
