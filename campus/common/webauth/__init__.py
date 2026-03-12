"""campus.common.webauth

Web authentication models for Campus Auth.

This module contains classes and functions for handling web-based
authentication schemes, including HTTP Basic and Bearer authentication,
as well as OAuth2 flows.

Session state is not handled.
"""

__all__ = [
    "http",
    "oauth2",
]

from . import http, oauth2
