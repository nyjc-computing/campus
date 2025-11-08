"""tests.fixtures.yapper

Functions for initialising campus.yapper for testing use
"""

from . import postgres, require, setup


def init():
    """Initialize yapper fixtures for testing.

    This function:
    - Ensures yapperdb database exists
    - Initializes 'yapper' vault label
    - Sets YAPPERDB_URI as a vault secret (not environment variable)
    - Gives client access to 'yapper' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Ensure database exists first
    postgres.ensure_database_exists("yapperdb")

    # Use the new auth resources instead of deprecated campus.vault
    from campus.auth.resources import vault as auth_vault
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    # Give test client access to yapper vault
    client_res = auth_client[client_id]
    client_res.access.grant("yapper", ModelClient.access.ALL)

    # Set up yapper vault with database URI as a secret
    yapper_vault = auth_vault["yapper"]
    db_uri = setup.get_db_uri("yapperdb")
    yapper_vault["YAPPERDB_URI"] = db_uri
