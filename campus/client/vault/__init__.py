"""campus.client.vault

Provides clean module interfaces for Campus Vault service resources.
"""

from campus import config
from campus.common.http import get_client

from .vault import VaultResource
from .access import VaultAccessResource
from .client import VaultClientResource


def get_vault() -> VaultResource:
    """Get the Vault service client."""
    vault_base_url = config.get_base_url("campus.vault")
    return VaultResource(get_client(base_url=vault_base_url))


__all__ = [
    'VaultAccessResource',
    'VaultClientResource',
    'VaultResource',
    'get_vault',
]
