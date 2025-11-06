"""campus.model.http.header

Campus model representation of HTTP headers.
"""

__all__ = [
    "HttpHeader",
]

from base64 import b64decode, b64encode


class HttpAuthProperty(str):
    """Authorization property for HTTP headers."""
    def __new__(cls, value: str):
        if not isinstance(value, str):
            raise TypeError("BasicAuthProperty must be a string")
        if not value.startswith("Basic ") and not value.startswith("Bearer "):
            raise ValueError(
                "Authorization header must start with 'Basic ' or 'Bearer '"
            )
        return str.__new__(cls, value)

    @property
    def scheme(self) -> str:
        """Return the authentication scheme."""
        scheme, _ = self.split(" ", 1)
        return scheme.lower()

    @property
    def token(self) -> str:
        """Return the value for the HTTP header."""
        scheme, key = self.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Only Bearer authentication has a direct value")
        return key.strip()

    def credentials(self, sep: str = ":") -> tuple[str, ...]:
        """Decode Base64-encoded credentials."""
        scheme, key = self.split(" ", 1)
        if scheme.lower() != "basic":
            raise ValueError("Only Basic authentication can be decoded")
        decoded = b64decode(key).decode("utf-8")
        assert sep in decoded, (
            f"Credentials must contain '{sep}' separator, got: {decoded}"
        )
        return tuple(decoded.split(sep))

    @classmethod
    def for_basic(
            cls,
            client_id: str,
            client_secret: str
    ) -> "HttpAuthProperty":
        """Create an HttpAuthProperty from client credentials."""
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = b64encode(credentials.encode()).decode()
        return cls(f"Basic {encoded_credentials}")

    @classmethod
    def for_bearer(cls, token: str) -> "HttpAuthProperty":
        """Create an HttpAuthProperty from a bearer token."""
        return cls(f"Bearer {token}")


class HttpHeader(dict):
    """HTTP header representation as a dictionary."""

    @property
    def authorization(self) -> HttpAuthProperty | None:
        """Get the authorization property from the header."""
        auth_header = self.get("Authorization")
        if auth_header:
            return HttpAuthProperty(auth_header)
        return None

    @classmethod
    def from_credentials(cls, c_id: str, c_secret: str) -> "HttpHeader":
        """Create an HTTP header dictionary from client credentials."""
        auth_property = HttpAuthProperty.for_basic(c_id, c_secret)
        return cls({"Authorization": auth_property})

    @classmethod
    def from_bearer_token(cls, token: str) -> "HttpHeader":
        """Create an HTTP header dictionary from a bearer token."""
        auth_property = HttpAuthProperty.for_bearer(token)
        return cls({"Authorization": auth_property})

    def user_agent(self) -> str | None:
        """Get the User-Agent header value."""
        return self.get("User-Agent", "Unknown")
