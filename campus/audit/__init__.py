"""campus.audit

Audit service for tracing and monitoring Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.audit only.
__all__ = ["init_app"]

from typing import Any

import campus_python
import flask

from campus.auth.middleware import Authenticator
from campus.common import env
from campus.common import schema
from campus.common.errors import auth_errors

# Other local imports are intentionally omitted to avoid circular
# dependencies.

# Lazily initialized campus client - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
# Type: ignore because we initialize these in init_app() before first use
campus: campus_python.Campus = None  # type: ignore


def _audit_getsecret(name: str) -> str:
    """Get secret from vault for campus.audit deployment.

    This function is registered with env.register_getsecret() to provide
    deployment-specific vault access for campus.audit.

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


# Create authenticator using campus_python (same as campus.api)
audit_authenticator = Authenticator(
    basic_authenticator=basic_authenticate,
    bearer_authenticator=bearer_authenticate,
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the audit blueprint with the given Flask app."""
    from campus.common import env

    # Register deployment-specific getsecret function
    env.register_getsecret(_audit_getsecret)

    # Initialize campus client after test fixtures have set up the vault
    global campus
    campus = campus_python.Campus(timeout=60)

    from . import routes, web

    # Create route blueprints using create_blueprint() for test isolation
    traces_blueprint = routes.traces.create_blueprint()
    health_blueprint = routes.health.create_blueprint()

    # Organise audit routes under audit blueprint
    bp = flask.Blueprint('audit_v1', __name__, url_prefix='/audit/v1')

    # Apply authentication to the traces blueprint (before registering)
    # This ensures only trace routes require auth, not health routes
    traces_blueprint.before_request(audit_authenticator.authenticate)

    # Register authenticated routes (traces)
    bp.register_blueprint(traces_blueprint)

    # Register public health routes WITHOUT authentication
    bp.register_blueprint(health_blueprint)

    app.register_blueprint(bp)

    # Register web UI blueprint (no authentication required for browsing)
    ui_blueprint = web.ui.create_blueprint()
    app.register_blueprint(ui_blueprint)

    if isinstance(app, flask.Flask):
        app.secret_key = env.getsecret("SECRET_KEY")
