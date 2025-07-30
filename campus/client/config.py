"""campus.client.config

Configuration for Campus client base URLs and service mappings.

This module provides environment-aware configuration for client base URLs
using the common.devops environment enums for consistency.
"""

from typing import Set
from campus.common import devops

# Service mappings - which services use which deployment
APPS_SERVICES: Set[str] = {
    "circles",
    "users",
    "emailotp",
    "clients"
}

VAULT_SERVICES: Set[str] = {
    "vault",
    "vault_access",
    "vault_client"
}


def get_apps_base_url() -> str:
    """Get the base URL for apps services based on environment.

    Returns:
        str: Base URL for apps deployment
    """
    match devops.ENV:
        case devops.PRODUCTION:
            return "https://api.campus.nyjc.app"
        case devops.STAGING:
            return "https://api.campus.nyjc.dev"
        case devops.TESTING | devops.DEVELOPMENT:
            return "https://campusapps-development.up.railway.app/"
    raise ValueError(f"Unknown environment: {devops.ENV}")


def get_vault_base_url() -> str:
    """Get the base URL for vault services based on environment.

    Returns:
        str: Base URL for vault deployment
    """
    match devops.ENV:
        case devops.PRODUCTION:
            return "https://vault.campus.nyjc.app"
        case devops.STAGING:
            return "https://vault.campus.nyjc.dev"
        case devops.TESTING | devops.DEVELOPMENT:
            return "https://campusvault-development.up.railway.app/"
    raise ValueError(f"Unknown environment: {devops.ENV}")


def get_service_base_url(service_name: str) -> str:
    """Get the appropriate base URL for a given service.

    Args:
        service_name: Name of the service (e.g., "circles", "vault")

    Returns:
        str: Base URL for the service's deployment

    Raises:
        ValueError: If service_name is not recognized
    """
    if service_name in APPS_SERVICES:
        return get_apps_base_url()
    elif service_name in VAULT_SERVICES:
        return get_vault_base_url()
    else:
        raise ValueError(f"Unknown service: {service_name}")


# Legacy constants for backward compatibility
# These are now environment-aware
APPS_BASE_URL = get_apps_base_url()
VAULT_BASE_URL = get_vault_base_url()
