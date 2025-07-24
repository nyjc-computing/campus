"""Campus Vault service clients.

Provides clean module interfaces for Campus Vault service resources.
"""

from campus.client.vault import vault
from campus.client.vault import access
from campus.client.vault import client

__all__ = ['vault', 'access', 'client']
