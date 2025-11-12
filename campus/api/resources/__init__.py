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
]

from .circle import CirclesResource
from .emailotp import EmailOTPResource

# Initialize resource instances for internal use
circle = CirclesResource()
emailotp = EmailOTPResource()
