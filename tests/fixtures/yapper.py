"""tests.fixtures.yapper

Functions for initialising campus.yapper for testing use
"""

from . import postgres, require, setup

# Module-level variable to track if yapper was initialized
_yapper_db_path = None


def init():
    """Initialize yapper fixtures for testing.

    This function:
    - Ensures yapperdb database exists (skipped in SQLite test mode)
    - Initializes 'yapper' vault label
    - Sets YAPPERDB_URI as a vault secret (not environment variable)
    - Gives client access to 'yapper' label

    ENV must be 'testing' and client credentials must be set before calling.

    This function is idempotent - calling it multiple times will reuse the
    same database file.
    """
    global _yapper_db_path
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

    # Check if already initialized (idempotent)
    if _yapper_db_path is not None:
        db_uri = _yapper_db_path
    elif campus.storage.testing.is_test_mode():
        # Use a temp file for the database
        # Note: :memory: doesn't work because each connection creates a new empty DB
        import tempfile
        import os
        fd, db_path = tempfile.mkstemp(suffix='.sqlite', prefix='yapperdb_')
        os.close(fd)
        db_uri = db_path
        _yapper_db_path = db_path
        # Store path for cleanup
        yapper_vault["YAPPERDB_PATH"] = db_path
    else:
        db_uri = setup.get_db_uri("yapperdb")
    yapper_vault["YAPPERDB_URI"] = db_uri
