"""campus.client.config

Configuration for Campus base URLs and service mappings.

This module provides environment-aware configuration for client base URLs
using the common.devops environment enums for consistency.
"""

from campus.common import devops


Url = str

BASE_URLS = {
    "campus.vault": {
        devops.PRODUCTION: "https://vault.campus.nyjc.app/api/v1/",
        devops.STAGING: "https://vault.campus.nyjc.dev/api/v1/",
        devops.TESTING: "vault.campus.testing/",
        devops.DEVELOPMENT: "https://campusvault-development.up.railway.app/api/v1/",
    },
    "campus.apps": {
        devops.PRODUCTION: "https://api.campus.nyjc.app/api/v1/",
        devops.STAGING: "https://api.campus.nyjc.dev/api/v1/",
        devops.TESTING: "apps.campus.testing/",
        devops.DEVELOPMENT: "https://campusapps-development.up.railway.app/api/v1/",
    }
}


def get_app_base_url(app_name: str) -> Url:
    """Get the base URL for apps services based on environment.

    Returns:
        str: Base URL for apps deployment
    """
    if app_name not in BASE_URLS:
        raise ValueError(f"No base URL registered for app: {app_name}")
    app_envs = BASE_URLS[app_name]
    if devops.ENV not in app_envs:
        raise ValueError(
            f"No base URL registered for app: {app_name} in environment: {devops.ENV}")
    return app_envs[devops.ENV]
