"""tests.fixtures.yapper

Functions for initialising campus.yapper for testing use
"""

from . import require, setup


def init():
    """Initialize yapper fixtures for testing.

    This function:
    - Initializes 'yapper' vault label
    - Sets YAPPERDB_URI as a vault secret (not environment variable)
    - Gives client access to 'yapper' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    import campus.vault

    # Give test client access to yapper vault
    campus.vault.access.grant_access(
        client_id=client_id,
        label="yapper",
        access=campus.vault.access.ALL
    )

    # Set up yapper vault with database URI as a secret
    yapper_vault = campus.vault.get_vault("yapper")
    db_uri = setup.get_db_uri("yapperdb")
    yapper_vault.set("YAPPERDB_URI", db_uri)
