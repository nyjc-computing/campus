"""campus.api

Web API for Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.api only.
__all__ = ["init_app"]

from typing import Any

import campus_python
import flask

from campus.auth.middleware import Authenticator
from campus.common import schema
from campus.common.errors import auth_errors

# Other local imports are intentionally omitted to avoid circular
# dependencies.

# Lazily initialized campus client - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
# Type: ignore because we initialize these in init_app() before first use

campus: campus_python.Campus = None  # type: ignore


def _api_getsecret(name: str) -> str:
    """Get secret from vault for campus.api deployment.

    This function is registered with env.register_getsecret() to provide
    deployment-specific vault access for campus.api.

    Args:
        name: Name of the secret to retrieve

    Returns:
        The secret value from the vault

    Raises:
        OSError: If DEPLOY environment variable is not set
        api_errors.InternalError: If the secret is not found in the vault
    """
    from campus.common import env
    from campus.common.errors import api_errors

    deployment = env.get("DEPLOY")
    if deployment is None:
        raise OSError("Environment variable 'DEPLOY' required")

    import campus_python
    campus_auth = campus_python.Campus(timeout=60).auth
    try:
        return campus_auth.vaults[deployment][name]
    except KeyError:
        raise api_errors.InternalError(
            f"Vault secret '{name}' not found in label '{deployment}'"
        )


def basic_authenticate(client_id: str, client_secret: str) -> dict[str, Any]:
    """Authenticate using HTTP Basic Authentication."""
    try:
        auth_result = campus.auth.root.authenticate(
            client_id=schema.CampusID(client_id),
            client_secret=client_secret
        )
    except campus_python.errors.AuthenticationError:
        raise auth_errors.UnauthorizedClientError(
            "Invalid client credentials"
        )
    return {
        "client": auth_result["client"],
        "user": None,
    }

def bearer_authenticate(token: str) -> dict[str, Any]:
    """Authenticate using HTTP Bearer Authentication."""
    try:
        auth_result = campus.auth.root.authenticate(token=token)
    except campus_python.errors.AuthenticationError:
        raise auth_errors.UnauthorizedClientError(
            "Invalid access token"
        )
    return {
        "client": auth_result["client"],
        "user": auth_result.get("user"),
    }

# Create authenticator using campus_python
campus_authenticator = Authenticator(
    basic_authenticator=basic_authenticate,
    bearer_authenticator=bearer_authenticate,
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    from campus.common import env

    # Register deployment-specific getsecret function
    env.register_getsecret(_api_getsecret)

    # Initialize campus client after test fixtures have set up the vault
    global campus
    campus = campus_python.Campus(timeout=60)

    from . import routes

    # Organise API routes under api blueprint
    bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')
    routes.assignments.init_app(bp)
    routes.bookings.init_app(bp)
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.submissions.init_app(bp)

    # Apply authentication to all API routes
    bp.before_request(campus_authenticator.authenticate)

    app.register_blueprint(bp)

    if isinstance(app, flask.Flask):
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY")
