"""campus.auth.webauth

Web authentication models for Campus Auth.

This module contains classes and functions for handling web-based
authentication schemes, including HTTP Basic and Bearer authentication,
as well as OAuth2 flows.

Secure cookies are used client-side to maintain session state.
"""

__all__ = [
    "http",
    "oauth2",
]

from . import http, oauth2
