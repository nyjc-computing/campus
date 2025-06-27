"""apps/api/models/auth

Web authentication models for the Campus API.

This module contains classes and functions for handling web-based authentication
schemes, including HTTP Basic and Bearer authentication, as well as OAuth2
flows.

The classes do not authenticate credentials, but provide the necessary
configuration and validation methods for authentication headers. Actual
authentication logic is handled by the campusauth module.
"""

from apps.api.models.webauth.base import Security, SecurityScheme, SecuritySchemeConfigSchema
import apps.api.models.webauth.http as http
import apps.api.models.webauth.oauth2 as oauth2

SecurityScheme.register("http", http.HttpAuthenticationScheme)
SecurityScheme.register("oauth2", oauth2.OAuth2FlowScheme)


__all__ = [
    "Security",
    "SecurityScheme",
    "SecuritySchemeConfigSchema",
    "http",
    "oauth2",
]
