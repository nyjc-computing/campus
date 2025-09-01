"""campus.client.vault

Provides clean module interfaces for Campus Vault service resources.
"""

from campus import config
from campus.common.http import get_client

from .vault import VaultResource
from .access import VaultAccessResource
from .client import VaultClientResource


def get_vault(*, raw: bool = False) -> VaultResource:
    """Get the Vault service client.

    Args:
        raw: If True, methods return JsonResponse objects.
             If False (default), methods call raise_for_status() and return JSON data.
    """
    vault_base_url = config.get_base_url("campus.vault")
    return VaultResource(get_client(base_url=vault_base_url), raw=raw)


__all__ = [
    'VaultAccessResource',
    'VaultClientResource',
    'VaultResource',
    'get_vault',
]
