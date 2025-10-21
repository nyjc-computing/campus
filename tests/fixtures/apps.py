"""tests.fixtures.apps

Functions for initialising campus.apps for testing use
"""

from . import require


def init():
    """Initialize apps fixtures for testing.

    This function:
    - Sets up campus SECRET_KEY in 'campus' vault
    - Gives client access to 'campus' label

    ENV must be 'testing' and client credentials must be set before calling.
    This should be called after vault fixtures are initialized.

    Apps service uses the storage abstraction, so no direct database setup needed.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Set up campus SECRET_KEY in campus vault
    import campus.vault
    campus_vault = campus.vault.get_vault("campus")
    campus_vault.set("SECRET_KEY", "campus-secret-key")

    # Give test client access to campus vault
    campus.vault.access.grant_access(
        client_id=client_id,
        label="campus",
        access=campus.vault.access.ALL
    )
