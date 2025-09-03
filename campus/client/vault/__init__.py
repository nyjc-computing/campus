"""campus.client.vault

Provides clean module interfaces for Campus Vault service resources.
"""

from typing import Callable

import campus.config
from campus.common.http import get_client

from .vault import VaultResource
from .access import VaultAccessResource
from .client import VaultClientResource

# Global vault factory that can be overridden for testing
_vault_factory: Callable[[], VaultResource] | None = None


def set_vault_factory(factory: Callable[[], VaultResource] | None) -> None:
    """Set a custom vault factory function.

    This allows overriding how vault clients are created, which is useful
    for testing where you want to use Flask test clients instead of real HTTP clients.

    Args:
        factory: Function that returns a VaultResource, or None to reset to default
    """
    global _vault_factory
    _vault_factory = factory


def get_vault(*, raw: bool = False) -> VaultResource:
    """Get the Vault service client.

    Args:
        raw: If True, methods return JsonResponse objects.
             If False (default), methods call raise_for_status() and return JSON data.
    """
    if _vault_factory is not None:
        return _vault_factory()

    vault_base_url = campus.config.get_base_url("campus.vault")
    return VaultResource(get_client(base_url=vault_base_url), raw=raw)


__all__ = [
    'VaultAccessResource',
    'VaultClientResource',
    'VaultResource',
    'get_vault',
    'set_vault_factory',
]
