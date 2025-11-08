"""tests.fixtures.api

Functions for initialising campus.api for testing use
"""

from . import require


def init():
    """Initialize API fixtures for testing.

    This function:
    - Sets up campus.api SECRET_KEY in 'campus.api' vault
    - Gives client access to 'campus.api' label

    ENV must be 'testing' and client credentials must be set before calling.
    This should be called after vault fixtures are initialized.

    Note: campus.api is a separate deployment that accesses campus.auth via campus_python.
    However, for testing purposes, we directly manipulate the auth resources to set up
    the necessary vault data without needing to make HTTP calls.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Set up campus.api SECRET_KEY in the "campus.api" vault using auth resources
    # This is acceptable in tests since we're testing both services in the same process
    from campus.auth.resources import vault as auth_vault
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    api_vault = auth_vault["campus.api"]
    api_vault["SECRET_KEY"] = "campus-api-secret-key"

    # Give test client access to campus.api vault
    client_res = auth_client[client_id]
    client_res.access.grant("campus.api", ModelClient.access.ALL)
