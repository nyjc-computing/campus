"""campus.auth.resources

Namespace for ampus.auth resources.
Note: These resources directly access storage without authentication,
and with minimal model-based validation.
They are intended for internal use within campus.auth.
External clients should access resources via API.
"""

__all__ = [
    "access",
    "client",
    "credentials",
    "login",
    "session",
    "user",
    "vault",
]

from . import(
    access,
    client,
    credentials,
    login,
    session,
    user,
    vault,
)
