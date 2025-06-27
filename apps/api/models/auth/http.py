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

    def get_auth_headers(self, **kwargs) -> dict:
        """Return headers or params for authenticated requests."""
        match self.scheme:
            case "basic":
                return {"Authorization": f"Basic {kwargs['credentials']}"}
            case "bearer":
                return {"Authorization": f"Bearer {kwargs['token']}"}
        raise ValueError(f"Unsupported HTTP auth scheme: {self.scheme}")

    def has_auth(self, header: HttpHeader) -> bool:
        """Check if authentication credentials are present in the request."""
        if not "Authorization" in header:
            return False
        match self.scheme:
            case "basic":
                return (
                    header["Authorization"].startswith("Basic ")
                    and len(header["Authorization"].split(" ")) == 2
                )
            case "bearer":
                return (
                    header["Authorization"].startswith("Bearer ")
                    and len(header["Authorization"].split(" ")) == 2
                )
        return False

    def is_valid(self, header: HttpHeader) -> bool:
        """Validate authorization header in the request."""
        if not self.has_auth(header):
            raise HttpSecurityError("Invalid authentication header.")
        match header["Authorization"].split(" "):
            case ["Basic", credentials]:
                # base64 decode
                # authenticate client_id and client_secret
                raise NotImplementedError
            case ["Bearer", token]:
                # validate JWT token
                # check token expiration and signature
                # authenticate user
                raise NotImplementedError
        raise HttpSecurityError("Invalid authentication header format.")

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
