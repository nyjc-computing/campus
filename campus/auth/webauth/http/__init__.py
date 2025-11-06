"""campus.auth.webauth.http

HTTP Authentication configs and models.

The HTTP authentication scheme comprises two types of authentication:
1. Basic Authentication: Uses a client_id and client_secret encoded in Base64.
2. Bearer Authentication: Uses a token (e.g., JWT) in the Authorization header
"""

__all__ = [
    "HttpAuthenticationScheme",
    "HttpScheme",
]

from typing import Literal

from campus.common.errors import api_errors, token_errors

from .. import base
from . import header

HttpScheme = Literal["basic", "bearer"]


class HttpAuthenticationScheme(base.SecurityScheme):
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
            *,
            header: header.HttpHeader | None = None
    ):
        super().__init__(provider)
        self.scheme = scheme  # type: ignore[assignment]
        self.header = header

    @classmethod
    def from_header(
            cls,
            *,
            provider: str,
            http_header: dict
    ) -> "HttpAuthenticationScheme":
        """Create an HTTP authentication scheme from an HTTP header."""
        header_ = header.HttpHeader(http_header)
        if header_.authorization is None:
            api_errors.raise_api_error(401)
        match header_.authorization.scheme:
            case "basic":
                return cls(provider, scheme="basic", header=header_)
            case "bearer":
                return cls(provider, scheme="bearer", header=header_)
        raise token_errors.InvalidClientError(
            f"Unsupported HTTP scheme: {header_.authorization.scheme}"
        )

    def verify_credentials(
            self,
            client_id: str,
            client_secret: str
    ) -> bool:
        """Verify client credentials for Basic Authentication.

        Raises an InvalidClientError if the scheme is not Basic.

        Returns:
            bool: True if credentials are valid, False otherwise.
        """
        if not self.header:
            raise ValueError("No HTTP header provided")
        if not self.header.authorization:
            raise ValueError("No Authorization property in HTTP header")
        if self.scheme != "basic":
            raise ValueError(
                "Credential verification is only applicable for "
                "Basic Authentication."
            )
        cred_client_id, cred_client_secret = (
            self.header.authorization.credentials()
        )
        return (
            cred_client_id == client_id and
            cred_client_secret == client_secret
        )

    def verify_token(self, token: str) -> bool:
        """Verify token for Bearer Authentication.

        Raises an InvalidClientError if the scheme is not Bearer.

        Returns:
            bool: True if token is valid, False otherwise.
        """
        if not self.header:
            raise ValueError("No HTTP header provided")
        if not self.header.authorization:
            raise ValueError("No Authorization property in HTTP header")
        if self.scheme != "bearer":
            raise ValueError(
                "Token verification is only applicable for "
                "Bearer Authentication."
            )
        return self.header.authorization.token == token
