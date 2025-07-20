"""apps.common.webauth

Web authentication models for the Campus API.

This module contains classes and functions for handling web-based authentication
schemes, including HTTP Basic and Bearer authentication, as well as OAuth2
flows.

The classes do not authenticate credentials, but provide the necessary
configuration and validation methods for authentication headers. Actual
authentication logic is handled by the campusauth module.
"""

from . import http, oauth2
from .base import SecurityScheme

__all__ = [
    "SecurityScheme",
    "http",
    "oauth2",
]
