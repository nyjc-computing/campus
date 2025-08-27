"""campus.client.vault

Provides clean module interfaces for Campus Vault service resources.
"""

from campus.config import get_app_base_url
from campus.client.vault.vault import VaultResource
from campus.client.vault.access import VaultAccessResource
from campus.client.vault.client import VaultClientResource
from campus.common.http import get_client


def get_vault() -> VaultResource:
    """Get the Vault service client."""
    vault_base_url = get_app_base_url("campus.vault")
    return VaultResource(get_client(base_url=vault_base_url))


__all__ = [
    'VaultAccessResource',
    'VaultClientResource',
    'VaultResource',
    'get_vault',
]
