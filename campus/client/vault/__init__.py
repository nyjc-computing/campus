"""campus.client.vault

Provides clean module interfaces for Campus Vault service resources.
"""

from . import access, client, vault
from .vault import VaultClient

__all__ = [
    'access',
    'client',
    'vault',
    'VaultClient',
]
