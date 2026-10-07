"""campus.audit

Audit service for tracing and monitoring Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.audit only.
__all__ = ["init_app"]

import logging

import flask

from campus import webauth
from campus.common.errors import api_errors, auth_errors
from campus.common.utils import secret

from . import resources
from .helpers import audit_events

logger = logging.getLogger(__name__)


def _authenticate_audit_api_key() -> None:
    """Validate API key for audit endpoints using webauth.

    This function does not use campus.auth to avoid circular
    dependencies.

    Sets flask.g.api_key_id for tracing middleware.

    Raises:
        UnauthorizedError: if API key is invalid or missing

    """
    import time

    from campus.common import schema

    from .helpers.audit_events import FlaskResponseContext, _extract_request_context, emit_audit_event

    request_context = _extract_request_context(flask.request)
    started_at = schema.DateTime.utcnow()
    start_ns = time.perf_counter_ns()

    # Create minimal response context for auth events (no real response yet)
    def make_response_context(status_code: int) -> FlaskResponseContext:
        return {
            "status_code": status_code,
            "headers": {},
            "body": {},
        }

    try:
        httpauth = webauth.http.HttpAuthenticationScheme.with_header(
            provider="campus",
            http_header=dict(flask.request.headers)
        )
    except auth_errors.AuthorizationError:
        # No Authorization header present - emit audit event and raise proper error for 401 response
        emit_audit_event(
            data={"event_type": "audit.apikeys.auth.failed", "reason": "Missing API key"},
            api_key_id=None,
            parent_span_id=None,
            started_at=started_at,
            duration_ms=(time.perf_counter_ns() - start_ns) / 1_000_000,
            request_context=request_context,
            response_context=make_response_context(401),
        )
        raise api_errors.UnauthorizedError("Missing API key") from None

    # The audit API only accepts Bearer auth with audit API keys;
    # reject other schemes (e.g. Basic) with a clear 401 rather than
    # the scheme-mismatch error from .token (#699)
    if httpauth.scheme != "bearer":
        emit_audit_event(
            data={"event_type": "audit.apikeys.auth.failed", "reason": "Unsupported authentication scheme"},
            api_key_id=None,
            parent_span_id=None,
            started_at=started_at,
            duration_ms=(time.perf_counter_ns() - start_ns) / 1_000_000,
            request_context=request_context,
            response_context=make_response_context(401),
        )
        raise api_errors.UnauthorizedError(
            "Bearer authentication with an audit API key is required"
        )

    # Extract API key from Bearer token
    api_key = httpauth.token

    # Validate format
    if not secret.is_valid_audit_api_key_format(api_key):
        emit_audit_event(
            data={"event_type": "audit.apikeys.auth.failed", "reason": "Invalid API key format"},
            api_key_id=None,
            parent_span_id=None,
            started_at=started_at,
            duration_ms=(time.perf_counter_ns() - start_ns) / 1_000_000,
            request_context=request_context,
            response_context=make_response_context(401),
        )
        raise api_errors.UnauthorizedError(
            "Invalid API key format. Expected: audit_v1_<22-char-base64url>"
        )

    # Verify against database
    api_key_record = resources.apikeys.verify(api_key)
    if not api_key_record:
        emit_audit_event(
            data={"event_type": "audit.apikeys.auth.failed", "reason": "Invalid API key"},
            api_key_id=None,
            parent_span_id=None,
            started_at=started_at,
            duration_ms=(time.perf_counter_ns() - start_ns) / 1_000_000,
            request_context=request_context,
            response_context=make_response_context(401),
        )
        raise api_errors.UnauthorizedError("Invalid API key")

    # Success - emit audit event
    emit_audit_event(
        data={
            "event_type": "audit.apikeys.auth.success",
            "api_key_id": api_key_record.id,
        },
        api_key_id=api_key_record.id,
        parent_span_id=None,
        started_at=started_at,
        duration_ms=(time.perf_counter_ns() - start_ns) / 1_000_000,
        request_context=request_context,
        response_context=make_response_context(200),
    )

    flask.g.api_key_id = api_key_record.id
    # Scopes for the authorization layer (@require_scopes, #575)
    flask.g.api_key_scopes = list(api_key_record.scopes)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the audit blueprint with the given Flask app."""
    from campus.common.errors import handlers

    from . import routes, web

    # Ensure audit tables exist (idempotent CREATE TABLE IF NOT EXISTS),
    # mirroring auth's startup init for ClientsResource.
    from .resources.apikeys import APIKeysResource
    from .resources.ratelimit import init_storage as init_ratelimit_storage
    from .resources.traces import TracesResource
    APIKeysResource.init_storage()
    TracesResource.init_storage()
    init_ratelimit_storage()

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
    @audit_events.audit_event("audit.health.check")
    def health_check(**_) -> flask_campus.JsonResponse:
        """Health check endpoint (no authentication required).

        Returns:
            - 200 OK with {"status": "ok"} for JSON Accept header
            - 200 OK with "OK" plain text for text/plain Accept header
        """
        return {"status": "ok"}, 200

    app.register_blueprint(bp)

    # Register web UI blueprint, gated by the browser OAuth flow
    # (docs/web-ui-requirements.md §5; issue #696): unauthenticated
    # page requests redirect to /audit/login.
    ui_blueprint = web.ui.create_blueprint()
    ui_blueprint.before_request(web.auth.require_login_page)
    app.register_blueprint(ui_blueprint)

    # Register UI data endpoints (in-process data for the UI's
    # JavaScript), gated by the same login session; fetch() callers get
    # a 401 JSON response instead of a redirect.
    data_blueprint = web.data.create_blueprint()
    data_blueprint.before_request(web.auth.require_login_api)
    app.register_blueprint(data_blueprint)

    # Register the OAuth gate routes (login/callback/logout) last: they
    # must stay reachable without a session.
    app.register_blueprint(web.auth.create_blueprint())

    if isinstance(app, flask.Flask):
        # Service root / (#842): audit has a web UI, so it serves the
        # public landing page at the hostname root (campus-wide
        # convention: / is a landing page, /health is the health check;
        # deploy.configure_* adds /health). Standalone deployments only.
        app.register_blueprint(web.ui.create_root_blueprint())
        # Register error handlers for proper error responses
        handlers.init_app(app)
        # Lazy import to allow env setup
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY")

    # Ensure the operator API key exists so API-key management survives
    # the loss of every other key (#796). Runs on every startup
    # (idempotent) so a database reset self-heals on the next deploy.
    # Same loud-but-non-fatal policy as campus.auth's _seed_public_client.
    _seed_operator_key()


def _seed_operator_key() -> None:
    """Seed the operator API key, logging loudly on failure.

    The operator key cannot be created through the authenticated HTTP
    API (chicken-and-egg: apikeys:write requires a key that holds it),
    so it is seeded directly against storage from the
    AUDIT_OPERATOR_API_KEY env var. A no-op when the variable is unset.

    Failure to seed is logged at ERROR level with the recovery command
    but does not abort startup, so an unrelated seed failure does not
    take down the rest of the audit service.
    """
    import campus.config
    from campus.common import env

    if not env.get("AUDIT_OPERATOR_API_KEY"):
        logger.debug(
            "AUDIT_OPERATOR_API_KEY not set; skipping operator key seed"
        )
        return
    try:
        from .resources.apikeys import ensure_operator_key
        if ensure_operator_key():
            logger.info(
                "Seeded audit operator key '%s'",
                campus.config.AUDIT_OPERATOR_API_KEY_ID,
            )
    except Exception:
        logger.exception(
            "Failed to seed audit operator key '%s': API-key management "
            "will be unavailable until the key exists. Recover with: "
            "python scripts/seed_audit_operator_key.py",
            campus.config.AUDIT_OPERATOR_API_KEY_ID,
        )
