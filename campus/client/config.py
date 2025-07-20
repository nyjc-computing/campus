"""client.config

Configuration for Campus client base URLs and service mappings.

This module provides deployment-agnostic configuration for client base URLs.
Base URLs should be explicitly specified per deployment rather than hardcoded.
"""

import os
from typing import Set

# Default base URLs - should be overridden per deployment
# These are fallback values only
DEFAULT_APPS_BASE_URL = "https://api.campus.nyjc.dev"
DEFAULT_VAULT_BASE_URL = "https://vault.campus.nyjc.dev"

# Environment variable names for base URL configuration
APPS_BASE_URL_ENV = "CAMPUS_APPS_BASE_URL"
VAULT_BASE_URL_ENV = "CAMPUS_VAULT_BASE_URL"

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
    """Get the base URL for apps services.
    
    Returns:
        str: Base URL for apps deployment, from environment or default
    """
    return os.getenv(APPS_BASE_URL_ENV, DEFAULT_APPS_BASE_URL)


def get_vault_base_url() -> str:
    """Get the base URL for vault services.
    
    Returns:
        str: Base URL for vault deployment, from environment or default
    """
    return os.getenv(VAULT_BASE_URL_ENV, DEFAULT_VAULT_BASE_URL)


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
# These will be deprecated in favor of the functions above
APPS_BASE_URL = get_apps_base_url()
VAULT_BASE_URL = get_vault_base_url()
