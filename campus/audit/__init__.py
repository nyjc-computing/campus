"""campus.audit

Audit service for tracing and monitoring Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.audit only.
__all__ = ["init_app"]

import logging
logger = logging.getLogger(__name__)

import flask

from campus.common import webauth
from campus.common.errors import auth_errors, api_errors
from campus.common.utils import secret

from . import resources


def _authenticate_audit_api_key() -> None:
    """Validate API key for audit endpoints using webauth.

    This function does not use campus.auth to avoid circular
    dependencies.

    Sets flask.g.api_key_id for tracing middleware.

    Raises:
        UnauthorizedError: if API key is invalid or missing

    """
    try:
        httpauth = webauth.http.HttpAuthenticationScheme.with_header(
            provider="campus",
            http_header=dict(flask.request.headers)
        )
    except auth_errors.AuthorizationError:
        # No Authorization header present - raise proper error for 401 response
        raise api_errors.UnauthorizedError("Missing API key")

    # Extract API key from Bearer token
    api_key = httpauth.token
    # Validate format
    if not secret.is_valid_audit_api_key_format(api_key):
        raise api_errors.UnauthorizedError(
            f"Invalid API key format. Expected: audit_v1_<22-char-base64url>"
        )
    api_key_id = resources.apikeys.verify(api_key)
    if not api_key_id:
        raise api_errors.UnauthorizedError("Invalid API key")
    flask.g.api_key_id = api_key_id


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the audit blueprint with the given Flask app."""
    from . import routes, web
    from campus.common.errors import handlers

    # Organise audit routes under audit blueprint
    bp = flask.Blueprint('audit_v1', __name__, url_prefix='/audit/v1')

    # Create route blueprints using create_blueprint() for test isolation
    traces_blueprint = routes.traces.create_blueprint()
    traces_blueprint.before_request(_authenticate_audit_api_key)
    bp.register_blueprint(traces_blueprint)

    apikeys_blueprint = routes.apikeys.create_blueprint()
    apikeys_blueprint.before_request(_authenticate_audit_api_key)
    bp.register_blueprint(apikeys_blueprint)

    # Register public health routes WITHOUT authentication
    import campus.flask_campus as flask_campus
    @bp.get("/health")
    def health_check() -> flask_campus.JsonResponse:
        """Health check endpoint (no authentication required).

        Returns:
            - 200 OK with {"status": "ok"} for JSON Accept header
            - 200 OK with "OK" plain text for text/plain Accept header
        """
        return {"status": "ok"}, 200

    app.register_blueprint(bp)

    # Register web UI blueprint (no authentication required for browsing)
    ui_blueprint = web.ui.create_blueprint()
    app.register_blueprint(ui_blueprint)

    if isinstance(app, flask.Flask):
        # Register error handlers for proper error responses
        handlers.init_app(app)
        # Lazy import to allow env setup
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY")
