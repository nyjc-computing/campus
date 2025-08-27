"""campus.client.vault

Provides clean module interfaces for Campus Vault service resources.
"""

from campus.client.vault import vault
from campus.client.vault import access
from campus.client.vault import client
from campus.client.vault.vault import VaultResource
from campus.client.wrapper import ClientFactory


def get_vault(client_factory: ClientFactory) -> VaultResource:
    """Get the Vault service client."""
    return VaultResource(client_factory(), "vault")


__all__ = ['vault', 'access', 'client', 'VaultResource', 'get_vault']
