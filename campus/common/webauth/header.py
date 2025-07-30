"""campus.common.webauth.header

Utility functions and classes for handling HTTP headers
"""

from base64 import b64decode


class HttpAuthProperty(str):
    """Authentication property for HTTP headers."""
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
    def value(self) -> str:
        """Return the value for the HTTP header."""
        _, key = self.split(" ", 1)
        return key.strip()

    def credentials(self, sep: str = ":") -> tuple[str, ...]:
        """Decode Base64-encoded credentials."""
        if self.scheme != "basic":
            raise ValueError("Only Basic authentication can be decoded")
        decoded = b64decode(self.value).decode("utf-8")
        assert sep in decoded, (
            f"Credentials must contain '{sep}' separator, got: {decoded}"
        )
        return tuple(decoded.split(sep))

    @classmethod
    def from_credentials(cls, c_id: str, c_secret: str) -> "HttpAuthProperty":
        """Create an HttpAuthProperty from client credentials."""
        credentials = f"{c_id}:{c_secret}"
        encoded_credentials = b64decode(credentials.encode()).decode()
        return cls(f"Basic {encoded_credentials}")

    @classmethod
    def from_bearer_token(cls, token: str) -> "HttpAuthProperty":
        """Create an HttpAuthProperty from a bearer token."""
        return cls(f"Bearer {token}")


class HttpHeaderDict(dict):
    """HTTP header representation as a dictionary."""

    def get_auth(self) -> HttpAuthProperty | None:
        """Get the authentication property from the header."""
        auth_header = self.get("Authorization")
        if auth_header:
            return HttpAuthProperty(auth_header)
        return None

    @classmethod
    def from_credentials(cls, c_id: str, c_secret: str) -> "HttpHeaderDict":
        """Create an HTTP header dictionary from client credentials."""
        auth_property = HttpAuthProperty.from_credentials(c_id, c_secret)
        return cls({"Authorization": auth_property})
    
    @classmethod
    def from_bearer_token(cls, token: str) -> "HttpHeaderDict":
        """Create an HTTP header dictionary from a bearer token."""
        auth_property = HttpAuthProperty.from_bearer_token(token)
        return cls({"Authorization": auth_property})


__all__ = [
    "HttpAuthProperty",
    "HttpHeaderDict",
]
