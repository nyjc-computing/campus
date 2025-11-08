"""tests.fixtures.auth

Functions for initializing campus.auth service infrastructure for testing.

This module sets up the backend resources needed by campus.auth:
- Storage tables for vaults and clients
- Test client credentials
- Default vault secrets
- Access permissions
"""

import time

from . import postgres, require, setup
from campus.common import env


def init():
    """Initialize auth service infrastructure for testing.

    This function:
    - Initializes storage tables (vaults, clients)
    - Creates test client and sets CLIENT_ID/CLIENT_SECRET env vars
    - Sets up vault's own SECRET_KEY in 'vault' vault
    - Gives client access to 'vault' label

    ENV must be 'testing' and postgres env vars must be set before calling.
    """
    require.env("testing")

    # Initialize storage-backed vault and client resources for testing.
    # The project now uses resource-backed storage (campus.auth.resources).
    from campus.auth.resources import vault as auth_vault
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    # Initialize storage tables for vaults and clients using the proper
    # init_from_model method which uses _model_to_sql_schema internally
    auth_vault.init_storage()
    auth_client.init_storage()

    # Set up vault's own SECRET_KEY (for client secret hashing)
    # Store in the "vault" label (the vault service's own secrets)
    vault_res = auth_vault["vault"]
    vault_res["SECRET_KEY"] = "vault-secret-key"

    # Set in environment for code that reads env.SECRET_KEY directly
    env.SECRET_KEY = "vault-secret-key"

    # Create client for testing (use consistent name) using ClientsResource
    client_name = "test-client"
    client_obj = auth_client.new(
        name=client_name, description="Campus test client")

    # Generate and store a secret for the client (ClientResource.revoke sets a new secret)
    client_id = client_obj.id
    client_res = auth_client[client_id]
    secret = client_res.revoke()

    # Set client credentials in environment
    env.CLIENT_ID = client_id
    env.CLIENT_SECRET = secret

    # Give client access to vault label
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
    """Give the configured client access to the labelled vault."""
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")

    # all cannot be specified with the other access levels
    if all and (read or create or update or delete):
        raise ValueError("Cannot specify 'all' with other access values")

    # Use the new auth resources instead of deprecated campus.vault
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    client_res = auth_client[client_id]
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
