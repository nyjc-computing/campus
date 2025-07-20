"""vault

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

import os

from flask import Blueprint, Flask

from campus.common import devops

from . import access, db, client
from .model import Vault, VaultKeyError
from .auth import VaultAuthError, ClientAuthenticationError, VaultAccessDeniedError

__all__ = [
    "get_vault",
    "get_authenticated_vault",
    "Vault",
    "AuthenticatedVault",
    "VaultKeyError", 
    "VaultAuthError",
    "ClientAuthenticationError",
    "VaultAccessDeniedError",
    "create_app",
    "init_app",
    "init_db",
    "access",
    "client",
]


def get_vault(label: str) -> Vault:
    """Get a Vault instance by label.
    
    This is a convenience function for programmatic access to vaults.
    For HTTP API access, use the routes which handle authentication.
    
    Note: When using this function programmatically, CLIENT_ID and CLIENT_SECRET
    environment variables must be set for the vault operations to work.
    
    For the new architecture, this returns a Vault model instance.
    Authentication and permission checking should be handled at the application layer.
    """
    return Vault(label)


class AuthenticatedVault:
    """Backward-compatible vault wrapper that includes authentication.
    
    This class provides the same interface as the old Vault class for
    backward compatibility, while using the new separated architecture.
    """
    
    def __init__(self, label: str):
        self.label = label
        self.vault = Vault(label)
        
        # Authenticate client using the new auth system
        from .auth import authenticate_client
        self.client_id = authenticate_client()
    
    def __repr__(self) -> str:
        return f"AuthenticatedVault(label={self.label!r})"
    
    def get(self, key: str) -> str:
        """Get a secret from the vault with authentication and permission checking."""
        from .auth import check_vault_access
        check_vault_access(self.client_id, self.label, access.READ)
        return self.vault.get(key)
    
    def has(self, key: str) -> bool:
        """Check if a secret exists in the vault with authentication and permission checking."""
        from .auth import check_vault_access
        check_vault_access(self.client_id, self.label, access.READ)
        return self.vault.has(key)
    
    def set(self, key: str, value: str) -> None:
        """Set a secret in the vault with authentication and permission checking."""
        from .auth import check_vault_access
        
        # Check if key exists to determine required permission
        key_exists = self.vault.has(key) if self._can_read() else False
        required_permission = access.UPDATE if key_exists else access.CREATE
        check_vault_access(self.client_id, self.label, required_permission)
        
        self.vault.set(key, value)
    
    def delete(self, key: str) -> None:
        """Delete a secret from the vault with authentication and permission checking."""
        from .auth import check_vault_access
        check_vault_access(self.client_id, self.label, access.DELETE)
        self.vault.delete(key)
    
    def _can_read(self) -> bool:
        """Check if client can read from this vault (for internal use)."""
        try:
            from .auth import check_vault_access
            check_vault_access(self.client_id, self.label, access.READ)
            return True
        except VaultAccessDeniedError:
            return False


def get_authenticated_vault(label: str) -> AuthenticatedVault:
    """Get an authenticated vault instance with the old interface.
    
    This function provides backward compatibility for code that expects
    the old Vault behavior with built-in authentication and permission checking.
    
    For new code, prefer using the routes for HTTP access or the model.Vault
    class directly with explicit authentication handling.
    """
    return AuthenticatedVault(label)


def create_app() -> Flask:
    """Factory function to create the vault app.
    
    This is called if vault is run as a standalone app.
    """
    app = Flask(__name__)
    init_app(app)
    return app


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault blueprints with the given Flask app."""
    from flask import jsonify
    from .routes import init_vault_routes, init_access_routes, init_client_routes
    
    # Add health check endpoint directly to the app (not part of vault API)
    @app.route("/health")
    def health_check():
        """Health check endpoint for deployment monitoring"""
        return jsonify({"status": "healthy", "service": "campus-vault"})
    
    # Register all vault-related blueprints
    init_vault_routes(app)   # /vault/* - secret management
    init_access_routes(app)  # /access/* - access control  
    init_client_routes(app)  # /client/* - client management


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    """
    # Initialize vault table
    with db.get_connection_context() as conn:
        with conn.cursor() as cursor:
            vault_schema = """
                CREATE TABLE IF NOT EXISTS vault (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    label TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    UNIQUE(label, key)
                )
            """
            cursor.execute(vault_schema)

    # Initialize access control table
    access.init_db()

    # Initialize vault client table
    client.init_db()


def run_server():
    """Entry point for running vault as a standalone service"""
    import os
    
    app = create_app()
    
    # Replit configuration
    host = "0.0.0.0"
    port = 5000
    
    print(f"🔐 Starting Campus Vault Service on {host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    run_server()
