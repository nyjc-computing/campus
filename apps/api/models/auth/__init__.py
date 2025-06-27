"""apps/api/models/auth

Authentication models for the Campus API.
"""

from apps.api.models.auth.base import SecurityScheme
import apps.api.models.auth.http as http
import apps.api.models.auth.oauth2 as oauth2

SecurityScheme.register("http", http.HttpAuthenticationScheme)
SecurityScheme.register("oauth2", oauth2.OAuth2FlowScheme)

__all__ = [
    "SecurityScheme",
    "http",
    "oauth2",
]
