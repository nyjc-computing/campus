"""tests.fixtures.vault

Functions for initialising campus.vault for testing use
"""

import os

from . import require

def init_vault():
    """Populate campus.vault with required data for testing, and
    set the CLIENT_ID and CLIENT_SECRET env variables.

    ENV must be 'testing' and VAULTDB_URI must be set before calling
    this function.
    """
    require.env("testing")
    require.envvar("VAULTDB_URI")

    import campus.vault

    # Initialise postgresql tables
    campus.vault.init_db()
    # Create client for testing
    client, client_secret = campus.vault.client.create_client(
        name="test-client",
        description="Campus test client"
    )
    os.environ["CLIENT_ID"] = client["id"]
    os.environ["CLIENT_SECRET"] = client_secret

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