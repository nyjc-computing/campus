"""tests.fixtures.auth

Functions for initializing campus.auth service infrastructure for testing.

This module sets up the backend resources needed by campus.auth:
- Storage tables for vaults and clients
- Test client credentials
- Default vault secrets
- Access permissions
"""

from campus.common import env

from . import require


def init():
    """Initialize auth service infrastructure for testing.

    This function sets up the storage-backed resources and credentials needed
    for campus.auth service testing. It creates storage tables, generates test
    client credentials, and configures vault secrets.

    Steps performed:
    1. Initialize storage tables (vaults, clients) using model schemas
    2. Create a test client with generated credentials
    3. Set up the 'vault' vault's SECRET_KEY for client secret hashing
    4. Grant the test client full access to the 'vault' label

    Environment variables set:
    - SECRET_KEY: The vault service's secret key
    - CLIENT_ID: Test client identifier
    - CLIENT_SECRET: Test client secret for authentication

    Prerequisites:
    - ENV must be 'testing'
    - PostgreSQL environment variables must be configured
    """
    require.env("testing")

    # Initialize storage-backed resources for the auth service
    from campus.auth.resources import vault as auth_vault
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    # Initialize storage tables using model schemas
    # This creates the database tables with proper column definitions
    auth_vault.init_storage()
    auth_client.init_storage()

    # Configure the vault service's own SECRET_KEY
    # This key is used for hashing client secrets
    # Store in the "vault" label (the auth service's internal vault)
    vault_res = auth_vault["vault"]
    vault_res["SECRET_KEY"] = "vault-secret-key"

    # Also set in environment for code that reads env.SECRET_KEY directly
    env.SECRET_KEY = "vault-secret-key"

    # Create a test client for authentication in tests
    client_name = "test-client"
    client_obj = auth_client.new(
        name=client_name, description="Campus test client")

    # Generate a client secret (ClientResource.revoke() generates a new secret)
    client_id = client_obj.id
    client_res = auth_client[client_id]
    secret = client_res.revoke()

    # Set client credentials in environment for test authentication
    env.CLIENT_ID = client_id
    env.CLIENT_SECRET = secret

    # Grant the test client full access to the 'vault' label
    client_res.access.grant("vault", ModelClient.access.ALL)


def give_vault_access(
        label: str,
        *,
        read: bool | None = None,
        create: bool | None = None,
        update: bool | None = None,
        delete: bool | None = None,
        all: bool | None = None
):
    """Grant the test client access to a specific vault label.

    This function configures access permissions for the test client to access
    a vault with the given label. Access can be granted at different levels:
    read, create, update, delete, or all (full access).

    Args:
        label: The vault label to grant access to
        read: Grant read access (optional)
        create: Grant create access (optional)
        update: Grant update access (optional)
        delete: Grant delete access (optional)
        all: Grant full access - cannot be combined with other access levels

    Raises:
        ValueError: If 'all' is specified along with other access levels

    Prerequisites:
        - ENV must be 'testing'
        - CLIENT_ID environment variable must be set
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")

    # Validate that 'all' is not combined with specific access levels
    if all and (read or create or update or delete):
        raise ValueError("Cannot specify 'all' with other access values")

    # Use auth resources to configure client access permissions
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    client_res = auth_client[client_id]

    # Build access value from specified permissions
    access_value = 0
    if all:
        access_value = ModelClient.access.ALL
    else:
        if read:
            access_value += ModelClient.access.READ
        if create:
            access_value += ModelClient.access.CREATE
        if update:
            access_value += ModelClient.access.UPDATE
        if delete:
            access_value += ModelClient.access.DELETE

    client_res.access.grant(label, access_value)
