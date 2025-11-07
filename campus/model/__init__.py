"""campus.model

Models represent single entities in Campus API schema.

They are typically represented as a row in a table, or a document in a
document store.
More complex models may span multiple tables or collections.

Models are represented with dataclasses.
init parameters must be keyword-only; order of parameters should not
matter.
Models are expected to be used across the codebase; they should have
minimal dependencies, ideally none. Data processing logic should be
kept out of models.
"""

__all__ = [
    "AuthSession",
    "Circle",
    "Client",
    "ClientAccess",
    "EmailOTP",
    "HttpHeader",
    "HttpHeaderWithAuth",
    "LoginSession",
    "Model",
    "OAuthToken",
    "Token",
    "User",
    "UserCredentials",
    "Vault",
]

from .base import Model
from .circle import Circle
from .client import Client, ClientAccess
from .credentials import OAuthToken, UserCredentials
from .http.header import HttpHeader, HttpHeaderWithAuth
from .emailotp import EmailOTP
from .login import LoginSession
from .session import AuthSession
from .token import Token
from .user import User
from .vault import Vault
