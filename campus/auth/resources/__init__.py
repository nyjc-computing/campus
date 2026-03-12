"""campus.auth.resources

Namespace for campus.auth resources.
Note: These resources directly access storage without authentication,
and with minimal model-based validation.
They are intended for internal use within campus.auth.
External clients should access resources via API.
"""

__all__ = [
    "client",
    "credentials",
    "device_code",
    "login",
    "session",
    "user",
    "vault",
]

from .client import ClientsResource
from .credentials import CredentialsResource
from .device_code import DeviceCodeResource
from .login import LoginSessionsResource
from .session import AuthSessionsResource
from .user import UsersResource
from .vault import VaultsResource

client = ClientsResource()
credentials = CredentialsResource()
device_code = DeviceCodeResource()
login = LoginSessionsResource()
session = AuthSessionsResource()
user = UsersResource()
vault = VaultsResource()
