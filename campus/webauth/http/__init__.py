"""campus.webauth.http

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
from ..models import HttpHeader, HttpHeaderWithAuth

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
            header: HttpHeaderWithAuth
    ):
        super().__init__(provider)
        self.scheme = scheme
        self.header = header

    @classmethod
    def with_header(
            cls,
            *,
            provider: str,
            http_header: HttpHeaderWithAuth | dict[str, str]
    ) -> "HttpAuthenticationScheme":
        """Create an HTTP authentication scheme from an HTTP header."""
        import logging
        logger = logging.getLogger(__name__)
        header = HttpHeader.from_header(http_header)

        if not isinstance(header, HttpHeaderWithAuth):
            logger.warning("Missing Authorization header.")
            # RFC 7235: a request missing its authentication credentials
            # is Unauthorized (401), not an OAuth flow error (#614).
            raise api_errors.UnauthorizedError(
                "Missing Authorization header."
            )
        try:
            match header.authorization.scheme:
                case "basic":
                    # Parse the credentials here so malformed values
                    # (bad base64, missing separator) reject as 401 at
                    # the boundary instead of escaping as ValueError
                    # from later extraction (#725).
                    header.authorization.credentials()
                    return cls(provider, scheme="basic", header=header)
                case "bearer":
                    return cls(provider, scheme="bearer", header=header)
        except ValueError as err:
            # Malformed Authorization values (unknown scheme prefix,
            # undecodable Basic credentials) are authentication
            # failures, not server errors.
            raise api_errors.UnauthorizedError(
                f"Malformed Authorization header: {err}"
            ) from None
        raise token_errors.InvalidClientError(
            f"Unsupported HTTP scheme: {header.authorization.scheme}"
        )

    @property
    def credentials(self) -> tuple[str, str]:
        """Return the client_id and client_secret for Basic
        Authentication.

        Raises:
            InvalidRequestError: If the scheme is not Basic or if the
                Authorization header is missing.
        """
        if self.scheme != "basic":
            raise api_errors.InvalidRequestError(
                "Credentials only available for Basic Authentication."
            )
        return self.header.authorization.credentials()

    @property
    def token(self) -> str:
        """Return the token for Bearer Authentication.

        Raises:
            InvalidRequestError: If the scheme is not Bearer or if the
                Authorization header is missing.
        """
        if self.scheme != "bearer":
            raise api_errors.InvalidRequestError(
                "Token only available for Bearer Authentication."
            )
        return self.header.authorization.token

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
