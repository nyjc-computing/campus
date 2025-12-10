"""campus.auth

This module contains the OAuth2 authentication hub for Campus.

campus-auth manages authentication and authorization for Campus
applications, as well as serving as a proxy for auth with third-party
integrations.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.auth only.
__all__ = ["init_app", "get_yapper"]

import flask

# Module-level yapper instance shared across all routes
_yapper_instance = None


def get_yapper():
    """Get the module-wide yapper instance.
    
    Initializes yapper lazily if not already initialized.
    This should be called at app startup to avoid circular dependencies
    during request handling.
    """
    global _yapper_instance
    if _yapper_instance is None:
        import campus.yapper
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the Campus app with all modules.

    This function sets up all Campus apps components including API,
    authentication, and OAuth modules.

    Note: For creating new Flask applications, use the recommended
    pattern:
        from campus.common.devops.deploy import create_app
        import campus.apps
        app = create_app(campus.apps)

    This ensures proper error handling and deployment configuration.
    """
    from . import oauth_proxy, provider, routes

    bp = flask.Blueprint("auth", __name__, url_prefix="/auth/v1")
    provider.init_app(bp)
    oauth_proxy.init_app(bp)
    routes.init_app(bp)

    if isinstance(app, flask.Flask):
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY", env.DEPLOY)

    app.register_blueprint(bp)
