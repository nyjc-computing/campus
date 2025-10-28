"""campus.auth

This module contains the OAuth2 authentication hub for Campus.

campus-auth manages authentication and authhorization for Campus
applications, as well as serving as a proxy for auth with third-party
integrations.
"""

__all__ = ["init_app"]

import flask


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the Campus app with all modules.

    This function sets up all Campus apps components including API,
    authentication, and OAuth modules.

    Note: For creating new Flask applications, use the recommended pattern:
        from campus.common.devops.deploy import create_app
        import campus.apps
        app = create_app(campus.apps)

    This ensures proper error handling and deployment configuration.
    """
    # TODO: init blueprints for campus.auth
    # Use vault client to retrieve secret key since campus.apps deployment
    # does not have VAULTDB_URI env var
    from . import provider, routes

    bp = flask.Blueprint('auth', __name__, url_prefix='/auth')
    provider.init_app(bp)
    routes.init_app(bp)

    if isinstance(app, flask.Flask):
        from campus.client.vault import get_vault
        vault = get_vault()
        app.secret_key = vault["auth"]["SECRET_KEY"].get()["value"]
