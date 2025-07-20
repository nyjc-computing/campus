"""Campus Client Error Classes

Common error types used across all campus client modules.
"""


class CampusClientError(Exception):
    """Base exception for all campus client errors."""
    pass


class AuthenticationError(CampusClientError):
    """Raised when authentication fails."""
    pass


class AccessDeniedError(CampusClientError):
    """Raised when the client lacks required permissions."""
    pass


class NotFoundError(CampusClientError):
    """Raised when a requested resource is not found."""
    pass


class ValidationError(CampusClientError):
    """Raised when input validation fails."""
    pass


class NetworkError(CampusClientError):
    """Raised when network communication fails."""
    pass
