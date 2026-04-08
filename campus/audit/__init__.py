"""campus.audit

Audit service for tracing and monitoring Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.audit only.
__all__ = ["init_app"]

from typing import Any

import flask

from campus.auth.middleware import Authenticator
from campus.common import env
from campus.common.errors import auth_errors

# Other local imports are intentionally omitted to avoid circular
# dependencies.


def bearer_authenticate(token: str) -> dict[str, Any]:
    """Authenticate using HTTP Bearer Authentication with audit API key.

    Validates audit API tokens. For now, this is a placeholder that
    stores the token in flask.g for later validation.

    TODO: Validate audit token against campus.auth or internal audit API keys.
    """
    # TODO: Implement proper audit API key validation
    # - Check against campus.auth credentials resources
    # - Or validate against internal audit API keys
    # For now, store the token in flask.g for later use
    return {
        "client": {"client_id": f"audit:{token}"},
        "user": None,
    }


# Create authenticator for audit (Bearer-only for API keys)
audit_authenticator = Authenticator(
    basic_authenticator=lambda client_id, client_secret: (_ for _ in ()).throw(
        auth_errors.InvalidRequestError("Only Bearer authentication supported for audit service")
    ),
    bearer_authenticator=bearer_authenticate,
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the audit blueprint with the given Flask app."""
    from . import routes

    # Organise audit routes under audit blueprint
    bp = flask.Blueprint('audit_v1', __name__, url_prefix='/audit/v1')

    # Register authenticated routes (traces)
    routes.traces.init_app(bp)

    # Apply authentication to the traces blueprint
    # Note: We apply to the traces blueprint directly so that health
    # routes can remain publicly accessible
    bp.before_request(audit_authenticator.authenticate)

    # Register public health routes WITHOUT authentication
    routes.health.init_app(bp)

    app.register_blueprint(bp)

    if isinstance(app, flask.Flask):
        app.secret_key = env.getsecret("SECRET_KEY", env.DEPLOY)
