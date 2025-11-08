"""tests.fixtures.api

Functions for initializing campus.api service fixtures for testing.

This module sets up vault secrets needed by campus.api service:
- SECRET_KEY for Flask session management
- Client access permissions for the api vault
"""

from . import auth, require


def init():
    """Initialize API service fixtures for testing.

    This function configures the vault infrastructure needed for campus.api
    service testing. It creates a vault labeled 'campus.api' with the necessary
    secrets and grants the test client access to it.

    Steps performed:
    1. Set SECRET_KEY in the 'campus.api' vault for Flask session management
    2. Grant the test client full access to the 'campus.api' vault

    Prerequisites:
    - ENV must be 'testing'
    - Auth fixtures must be initialized (CLIENT_ID must be set)
    """
    require.env("testing")

    # Set up the 'campus.api' vault with its SECRET_KEY for Flask sessions
    from campus.auth.resources import vault as auth_vault

    vault_res = auth_vault["campus.api"]
    vault_res["SECRET_KEY"] = "api-secret-key"

    # Grant the test client full access to the campus.api vault
    auth.give_vault_access("campus.api", all=True)
