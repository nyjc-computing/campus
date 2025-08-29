"""campus.vault.routes

Flask blueprint modules for the vault service.

This package contains all HTTP route definitions organized by functionality:
- vault.py: Secret management operations (/vault/*)
- access.py: Access control operations (/access/*)  
- client.py: Client management operations (/client/*)

Each module defines a Flask blueprint with appropriate URL prefixes and
authentication decorators.
"""

from . import vault, access, clients


__all__ = [
    "vault",
    "access",
    "clients",
]
