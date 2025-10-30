"""campus.models.webauth.http

HTTP Authentication configs and models.

The HTTP authentication scheme comprises two types of authentication:
1. Basic Authentication: Uses a client_id and client_secret encoded in Base64.
2. Bearer Authentication: Uses a token (e.g., JWT) in the Authorization header
"""

__all__ = [
    "HttpAuthenticationScheme",
    "HttpScheme",
    "HttpSecurityError",
]

from typing import Any, Literal, Mapping

from campus.common.errors import api_errors
from campus.models.webauth.header import HttpAuthProperty, HttpHeaderDict

from .base import SecurityError, SecurityScheme

HttpScheme = Literal["basic", "bearer"]


class HttpSecurityError(SecurityError):
    """HTTP authentication error."""


class HttpAuthenticationScheme(SecurityScheme):
    """HTTP authentication for Basic and Bearer schemes.

    This class provides methods to:
    - retrieve the authentication credentials from an HTTP header
    - validate the credentials against the configured scheme
    """
    security_scheme = "http"
    scheme: HttpScheme

    def __init__(
            self,
            provider: str,
            scheme: HttpScheme,
    ):
        super().__init__(provider)
        self.scheme = scheme  # type: ignore[assignment]

    @classmethod
    def from_header(
            cls,
            *,
            provider: str,
            header: dict
    ) -> "HttpAuthenticationScheme":
        """Create an HTTP authentication scheme from an HTTP header."""
        auth = HttpHeaderDict(header).get_auth()
        if auth is None:
            api_errors.raise_api_error(401)
        match auth.scheme:
            case "basic":
                return cls(provider, scheme="basic")
            case "bearer":
                return cls(provider, scheme="bearer")
        raise HttpSecurityError(f"Unsupported HTTP scheme: {auth.scheme}")

    def get_auth(self, *, header: Mapping[str, str]) -> HttpAuthProperty:
        """Validate the HTTP header for authentication.

        Raises an API error if the header is invalid or missing.

        Returns:
            HttpHeaderDict: The HTTP header dictionary containing the
            authentication information.
        """
        auth = HttpHeaderDict(header).get_auth()
        if auth is None:
            api_errors.raise_api_error(401)
        if auth.scheme != self.scheme:
            api_errors.raise_api_error(401)
        return auth
