"""tests.fixtures.yapper

Functions for initialising campus.yapper for testing use
"""

from . import postgres, require, setup


def init():
    """Initialize yapper fixtures for testing.

    This function:
    - Ensures yapperdb database exists (skipped in SQLite test mode)
    - Initializes 'yapper' vault label
    - Sets YAPPERDB_URI as a vault secret (not environment variable)
    - Gives client access to 'yapper' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Skip database setup if using in-memory SQLite for testing
    import campus.storage.testing
    if not campus.storage.testing.is_test_mode():
        postgres.ensure_database_exists("yapperdb")

    from campus.auth import resources as auth_resources
    from campus.model.client import ClientAccess

    # Give test client access to vault
    client_resource = auth_resources.client[client_id]
    client_resource.access.grant("yapper", ClientAccess.ALL)

    # Set up vault with database URI as a secret
    yapper_vault = auth_resources.vault["yapper"]

    # In test mode, use a dummy URI since we're using SQLite
    if campus.storage.testing.is_test_mode():
        db_uri = "sqlite:///:memory:"
    else:
        db_uri = setup.get_db_uri("yapperdb")
    yapper_vault["YAPPERDB_URI"] = db_uri
