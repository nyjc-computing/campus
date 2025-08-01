"""campus.vault.routes

Flask blueprint modules for the vault service.

This package contains all HTTP route definitions organized by functionality:
- vault.py: Secret management operations (/vault/*)
- access.py: Access control operations (/access/*)  
- client.py: Client management operations (/client/*)

Each module defines a Flask blueprint with appropriate URL prefixes and
authentication decorators.
"""

from .vault import init_app as init_vault_routes
from .access import init_app as init_access_routes  
from .client import init_app as init_client_routes

__all__ = [
    "init_vault_routes",
    "init_access_routes", 
    "init_client_routes"
]


def init_all_routes(app):
    """Initialize all vault-related routes with the given Flask app."""
    init_vault_routes(app)
    init_access_routes(app)
    init_client_routes(app)
