"""campus.client.errors

Common error types used across all campus client modules.
"""

# pylint: disable=unnecessary-ellipsis

class CampusClientError(Exception):
    """Base exception for all campus client errors."""
    ...

class AuthenticationError(CampusClientError):
    """Raised when authentication fails."""
    ...

class NetworkError(CampusClientError):
    """Raised when network communication fails."""
    ...

class MalformedResponseError(CampusClientError):
    """Raised when the API response is malformed."""
    ...
