"""campus.vault

Vault service for managing secrets and sensitive system data in Campus.

Each vault is identified by a unique label and stores key-value pairs of secrets.
Client access to vault labels is controlled through bitflag permissions.
Clients are identified and authenticated using CLIENT_ID and CLIENT_SECRET environment variables.

DATABASE ACCESS:
This service uses direct PostgreSQL connectivity instead of the storage module
to avoid circular dependencies. Since other services may depend on vault for
secrets management, vault must be independent of the storage layer. The vault
connects directly to PostgreSQL using the VAULTDB_URI environment variable.

CLIENT AUTHENTICATION:
The vault service maintains its own client storage system to avoid circular
dependencies with the main client model. Vault clients are stored in the
vault_clients table and authenticated using client ID and secret pairs.

Both CLIENT_ID and CLIENT_SECRET environment variables must be set:
- CLIENT_ID: Identifies the client making the request
- CLIENT_SECRET: Authenticates the client's identity

PERMISSION SYSTEM:
The vault uses bitflag permissions to control what operations clients can perform:

- READ (1): Can retrieve existing secrets with vault.get()
- CREATE (2): Can add new secrets with vault.set() (for new keys)
- UPDATE (4): Can modify existing secrets with vault.set() (for existing keys)  
- DELETE (8): Can remove secrets with vault.delete()

Permissions can be combined using the | operator:
- READ | CREATE: Can read and create, but not update or delete
- READ | UPDATE: Can read and modify existing secrets
- ALL: Can perform all operations (READ | CREATE | UPDATE | DELETE)

ARCHITECTURE:
This module follows separation of concerns:
- model.py: Pure data access layer (no auth/permissions)
- auth.py: Authentication and authorization utilities  
- routes/: HTTP routes with auth decorators organized by function
  - routes/vault.py: Secret management endpoints
  - routes/access.py: Access control endpoints
  - routes/client.py: Client management endpoints
- access.py: Permission checking logic
- client.py: Client management
- db.py: Database utilities

USAGE EXAMPLE:
    # Create vault client (typically done by admin)
    from vault.client import create_client
    client_resource, client_secret = create_client(
        name="my-app", 
        description="My application"
    )
    
    # Grant permissions (typically done by admin)
    from vault.access import grant_access, READ, CREATE
    grant_access(client_resource["id"], "api-secrets", READ | CREATE)
    
    # Use vault programmatically (CLIENT_ID and CLIENT_SECRET env vars must be set)
    vault = get_vault("api-secrets")
    vault.set("api_key", "secret123")  # Requires CREATE (new key)
    secret = vault.get("api_key")      # Requires READ
    vault.set("api_key", "newsecret")  # Requires UPDATE (existing key)
    vault.delete("api_key")            # Requires DELETE
    
    # Use vault via HTTP API
    # POST /vault/api-secrets/my_key with {"value": "secret123"}
    # GET /vault/api-secrets/my_key
    # DELETE /vault/api-secrets/my_key
"""

from flask import Blueprint, Flask

from campus.common import devops, errors

from . import access, client, db, vault

__all__ = [
    "get_vault",
    "create_app",
    "init_app",
    "init_db",
    "access",
    "client",
]


# This file uses local imports to avoid polluting global space
# pylint: disable=import-outside-toplevel

def get_vault(label: str) -> vault.Vault:
    """Get a Vault instance by label.

    This is a convenience function for programmatic access to vaults.
    For HTTP API access, use the routes which handle authentication.

    Note: When using this function programmatically, CLIENT_ID and CLIENT_SECRET
    environment variables must be set for the vault operations to work.

    For the new architecture, this returns a Vault model instance.
    Authentication and permission checking should be handled at the application layer.
    """
    return vault.Vault(label)


def create_app() -> Flask:
    """Factory function to create the vault app.

    This is called if vault is run as a standalone app.
    """
    app = Flask(__name__)
    init_app(app)
    errors.init_app(app)
    return app


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault blueprints with the given Flask app."""
    # Health check route for deployments
    @app.get('/')
    def health_check():
        return {'status': 'healthy', 'service': 'campus-vault'}, 200

    # Register all vault-related blueprints
    from . import routes
    routes.vaults.init_app(app)
    routes.access.init_app(app)
    routes.clients.init_app(app)


@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test or staging
    environment.
    """
    vault.init_db()
    client.init_db()
    access.init_db()
