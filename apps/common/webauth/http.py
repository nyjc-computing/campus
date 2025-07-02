"""apps.common.webauth.http

HTTP aAuthentication configs and models.

The HTTP authentication scheme comprises two types of authentication:
1. Basic Authentication: Uses a client_id and client_secret encoded in Base64.
2. Bearer Authentication: Uses a token (e.g., JWT) in the Authorization header
"""

from typing import Literal, Unpack

from apps.common.errors import api_errors
from common.auth.header import HttpAuthProperty, HttpHeaderDict
from common.integration.config import SecurityConfigSchema

from .base import SecurityError, SecurityScheme

HttpScheme = Literal["basic", "bearer"]


class HttpSecurityError(SecurityError):
    """HTTP authentication error."""


class HttpAuthConfigSchema(SecurityConfigSchema):
    """HTTP authentication scheme schema."""
    scheme: HttpScheme


class HttpAuthenticationScheme(SecurityScheme):
    """HTTP authentication for Basic and Bearer schemes."""
    scheme: HttpScheme

    def __init__(self, provider: str, **kwargs: Unpack[HttpAuthConfigSchema]):
        super().__init__(provider, **kwargs)
        self.scheme = kwargs["scheme"]

    def validate_header(self, header: dict) -> HttpAuthProperty:
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


__all__ = [
    "HttpAuthConfigSchema",
    "HttpAuthenticationScheme",
    "HttpScheme",
    "HttpSecurityError",
]
