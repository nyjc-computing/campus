"""campus.api.resources

Namespace for campus.api resources.
Note: These resources directly access storage without authentication,
and with minimal model-based validation.
They are intended for internal use within campus.api.
External clients should access resources via API endpoints.
"""

__all__ = [
    "circle",
    "emailotp",
    "session",
    "token",
    "user",
]

from .circle import CirclesResource, CircleMembersResource
from .emailotp import EmailOTPResource
from .session import SessionsResource
from .token import TokensResource
from .user import UsersResource

# Initialize resource instances for internal use
circle = CirclesResource()
emailotp = EmailOTPResource()
session = SessionsResource()
token = TokensResource()
user = UsersResource()
