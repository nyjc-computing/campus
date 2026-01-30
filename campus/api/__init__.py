"""campus.api

Web API for Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.api only.
__all__ = ["init_app"]

from typing import Any

import campus_python
import flask

from campus import flask_campus
from campus.common import env
from campus.common.errors import auth_errors

# Other local imports are intentionally omitted to avoid circular
# dependencies.

# Lazily initialized campus client - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
campus: campus_python.Campus | None = None
campus_auth: Any | None = None  # type: ignore
auth_root: Any | None = None  # type: ignore


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    global campus, campus_auth, auth_root

    # Initialize campus client after test fixtures have set up the vault
    campus = campus_python.Campus(timeout=60)
    campus_auth = campus.auth
    auth_root = campus.auth.root

    from campus.common import webauth

    from . import routes

    # Organise API routes under api blueprint
    bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')
    # Users need to be initialised first as other blueprints
    # rely on user table
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.assignments.init_app(bp)
    routes.submissions.init_app(bp)

    @bp.before_request
    def authenticate():
        """Check request header for authorization credentials.

        Push credential information to flask.g for use in route
        handlers.
        """
        httpauth = webauth.http.HttpAuthenticationScheme.with_header(
            provider="campus",
            http_header=flask_campus.get_request_headers()
        )
        match httpauth.header.authorization.scheme:
            case "basic":
                client_id, client_secret = (
                    httpauth.header.authorization.credentials()
                )
                try:
                    auth_result = campus_auth.root.authenticate(
                        client_id=client_id,  # type: ignore[arg-type]
                        client_secret=client_secret  # type: ignore[arg-type]
                    )
                except campus_python.errors.AuthenticationError:
                    auth_errors.UnauthorizedClientError(
                        "No Authorization header present"
                    )
                else:
                    flask.g.current_client = auth_result["client"]
            case "bearer":
                access_token = httpauth.header.authorization.token
                try:
                    auth_result = campus_auth.root.authenticate(
                        token=access_token)
                except campus_python.errors.AuthenticationError:
                    auth_errors.UnauthorizedClientError(
                        "No Authorization header present"
                    )
                else:
                    flask.g.current_client = auth_result["client"]
                    flask.g.current_user = auth_result["user"]

    app.register_blueprint(bp)

    if isinstance(app, flask.Flask):
        app.secret_key = env.getsecret("SECRET_KEY", env.DEPLOY)
