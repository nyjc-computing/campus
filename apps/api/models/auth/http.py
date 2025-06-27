"""apps/api/models/auth/authentication/http

HTTP aAuthentication configs and models.

The HTTP authentication scheme comprises two types of authentication:
1. Basic Authentication: Uses a client_id and client_secret encoded in Base64.
2. Bearer Authentication: Uses a token (e.g., JWT) in the Authorization header
"""

from typing import Literal, Unpack

from apps.api.models.auth.base import (
    BaseSecuritySchemeConfigSchema,
    HttpHeader,
    SecurityError,
    SecurityScheme
)
from apps.common.errors import api_errors
from common.auth.header import HttpHeaderDict

HttpScheme = Literal["basic", "bearer"]


class HttpSecurityError(SecurityError):
    """HTTP authentication error."""


class HttpAuthConfigSchema(BaseSecuritySchemeConfigSchema):
    """HTTP authentication scheme schema."""
    scheme: HttpScheme


class HttpAuthenticationScheme(SecurityScheme):
    """HTTP authentication for Basic and Bearer schemes."""
    scheme: HttpScheme

    def __init__(self, **kwargs: Unpack[HttpAuthConfigSchema]):
        super().__init__(**kwargs)
        self.scheme = kwargs["scheme"]

    def validate_header(self, header: HttpHeader) -> None:
        """Validate the HTTP header for authentication.
        
        Raises an API error if the header is invalid or missing.
        """
        auth = HttpHeaderDict(header).get_auth()
        if auth is None:
            api_errors.raise_api_error(401)
        if auth.scheme != self.scheme:
            api_errors.raise_api_error(401)
        
    @classmethod
    def from_json(
            cls,
            data: HttpAuthConfigSchema
    ) -> "HttpAuthenticationScheme":
        """Validate security_scheme before calling this method."""
        return cls(**data)


__all__ = [
    "HttpAuthConfigSchema",
    "HttpAuthenticationScheme",
    "HttpScheme",
    "HttpSecurityError",
]
