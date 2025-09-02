"""tests.fixtures.vault

Functions for initialising campus.vault for testing use
"""

import os

from . import require, setup
from .setup import set_db_uri


def init():
    """Initialize vault fixtures for testing.

    This function:
    - Sets up VAULTDB_URI using postgres env vars
    - Initializes vault database
    - Creates test client and sets CLIENT_ID/CLIENT_SECRET env vars
    - Sets up SECRET_KEY in 'vault' vault
    - Gives client access to 'vault' label

    ENV must be 'testing' and postgres env vars must be set before calling.
    """
    require.env("testing")
    setup.set_db_uri("VAULTDB_URI", "vaultdb")
    import campus.vault
    campus.vault.init_db()

    # Set up SECRET_KEY in vault vault first (needed for client creation)
    # We need to bootstrap this manually since there's no client yet
    from campus.vault.vault import Vault
    vault_instance = Vault("vault")
    vault_instance.set("SECRET_KEY", "vault-secret-key")

    # Create client for testing
    clientconfig = campus.vault.client.create_client(
        name="test-client",
        description="Campus test client"
    )
    client, secret = clientconfig["client"], clientconfig["secret"]

    # Set client credentials in environment
    os.environ["CLIENT_ID"] = client["id"]
    os.environ["CLIENT_SECRET"] = secret

    # Give client access to vault label
    campus.vault.access.grant_access(
        client_id=client["id"],
        label="vault",
        access=campus.vault.access.ALL
    )


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

    import campus.vault
    access_value = 0
    if all:
        access_value = campus.vault.access.ALL
    else:
        if read:
            access_value += campus.vault.access.READ
        if create:
            access_value += campus.vault.access.CREATE
        if update:
            access_value += campus.vault.access.UPDATE
        if delete:
            access_value += campus.vault.access.DELETE

    campus.vault.access.grant_access(
        client_id=client_id,
        label=label,
        access=access_value
    )
