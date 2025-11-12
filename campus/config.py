"""campus.config

Configuration for Campus base URLs and service mappings.

This module provides environment-aware configuration for service base URLs
using the common.devops environment enums for consistency.
"""

from campus.common import devops


Url = str

BASE_URLS = {
    "campus.auth": {
        devops.PRODUCTION: "https://auth.campus.nyjc.app/api/v1/",
        devops.STAGING: "https://auth.campus.nyjc.dev/api/v1/",
        devops.TESTING: "http://auth.campus.testing:8080/api/v1/",
        devops.DEVELOPMENT: "https://campusauth-development.up.railway.app/api/v1/",
    },
    "campus.api": {
        devops.PRODUCTION: "https://api.campus.nyjc.app/api/v1/",
        devops.STAGING: "https://api.campus.nyjc.dev/api/v1/",
        devops.TESTING: "http://api.campus.testing:8081/api/v1/",
        devops.DEVELOPMENT: "https://campusapi-development.up.railway.app/api/v1/",
    }
}


def get_base_url(app_name: str) -> Url:
    """Get the base URL for a service based on environment.

    Args:
        app_name: Service name (e.g., "campus.auth", "campus.api")

    Returns:
        str: Base URL for the service deployment
    """
    if app_name not in BASE_URLS:
        raise ValueError(f"No base URL registered for service: {app_name}")
    app_envs = BASE_URLS[app_name]
    if devops.ENV not in app_envs:
        raise ValueError(
            f"No base URL registered for service: {app_name} in environment: {devops.ENV}")
    return app_envs[devops.ENV]


DEFAULT_LOGIN_EXPIRY_DAYS = 30
DEFAULT_OAUTH_EXPIRY_MINUTES = 10
DEFAULT_TOKEN_EXPIRY_DAYS = 7

SUPPORTED_OAUTH2_GRANT_TYPES = ("code",)
