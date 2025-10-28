"""campus.auth

This module contains the OAuth2 authentication hub for Campus.

campus-auth manages authentication and authhorization for Campus
applications, as well as serving as a proxy for auth with third-party
integrations.
"""

__all__ = ["init_app"]

import flask

from campus.common import devops, env
from campus.models import session


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

    bp = provider.bp
    routes.init_app(bp)

    if devops.ENV == devops.DEVELOPMENT:
        # Add test login and logout endpoints in development environment
        auth_sessions = session.AuthSessions("campus")
        @bp.get("/test-login")
        def test_login():
            """Test login endpoint."""
            return flask.redirect(
                flask.url_for(
                    ".authorize",
                    client_id=env.CLIENT_ID,
                    response_type="code",
                    redirect_uri=flask.url_for(
                        ".callback",
                        _external=True,
                    ),
                    scope="profile email",
                    state="teststate",
                )
            )

        @bp.get("/success")
        def success():
            """Login success endpoint."""
            return "Login successful! <a href='/auth/logout'>Logout</a>"

        @bp.get("/logout")
        def logout():
            """Logout endpoint."""
            auth_sessions.delete()
            return flask.redirect("/auth/test-login")

    if isinstance(app, flask.Flask):
        from campus.client.vault import get_vault
        vault = get_vault()
        app.secret_key = vault["campus"]["SECRET_KEY"].get()["value"]

    app.register_blueprint(bp)