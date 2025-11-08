"""campus.auth

This module contains the OAuth2 authentication hub for Campus.

campus-auth manages authentication and authorization for Campus
applications, as well as serving as a proxy for auth with third-party
integrations.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.auth only.
__all__ = ["init_app"]

import flask


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

    bp = provider.bp
    oauth_proxy.init_app(bp)
    routes.init_app(bp)

    if isinstance(app, flask.Flask):
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY", env.DEPLOY)
    
    app.register_blueprint(bp)
