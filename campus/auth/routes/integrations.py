"""campus.auth.routes.integrations

Read-only integrations registry endpoint (#688, #733 Phase 2).

`GET /integrations/v1/` publishes the in-code registry
(`campus.auth.integrations.REGISTRY`) for consumers: which first-party
integrations Campus offers, their public metadata, their configured
scope cap, and whether the connect flow is open. This is service
catalog data — vault CLIENT_ID/CLIENT_SECRET never appear here, and
the endpoint is public (like the OAuth proxy routes): everything it
returns is already observable by starting a connect flow.

Presentation concerns (icons, per-app marketing copy) stay
consumer-side; consumers build their connect links from
`authorize_path` + `base_provider`/`slug`.
"""

__all__ = [
    "bp",
    "create_blueprint",
    "init_app",
]

import flask

from campus import flask_campus
from campus.common.errors import api_errors

from .. import integrations

# Public blueprint: registered outside the authenticated routes (and
# outside /auth/v1) so consumers reach the catalog at /integrations/v1.
bp = flask.Blueprint('integrations', __name__, url_prefix='/integrations')


@bp.get("/v1/")
def list_integrations() -> flask_campus.JsonResponse:
    """List the first-party integrations Campus offers (#688).

    GET /integrations/v1/
    Auth: public.
    Returns: [
        {
            "provider": "google.classroom",
            "slug": "classroom",
            "base_provider": "google",
            "title": "Google Classroom",
            "description": "...",
            "scopes": ["..."],          (the integration's scope cap)
            "connectable": true,        (configured AND connect open)
            "authorize_path": "/auth/v1/google/classroom/authorize"
        }
    ]

    `connectable` is computed from the vault label at call time:
    false for an unconfigured registry stub (no upstream OAuth
    client) or when CONNECT_TARGETS is empty (connect disabled,
    fail-closed) — mirroring the guards the authorize route enforces.
    """
    entries = []
    for integration in integrations.REGISTRY.values():
        try:
            config = integrations.get_config(integration)
            connectable = bool(config.connect_targets)
            scope_cap = list(config.scopes)
        except api_errors.NotFoundError:
            # Inert stub: registered but with no upstream OAuth client
            connectable = False
            scope_cap = []
        entries.append({
            "provider": integration.provider,
            "slug": integration.slug,
            "base_provider": integration.base_provider,
            "title": integration.title,
            "description": integration.description,
            "scopes": scope_cap,
            "connectable": connectable,
            "authorize_path": (
                f"/auth/v1/{integration.base_provider}/"
                f"{integration.slug}/authorize"
            ),
        })
    return entries, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation."""
    new_bp = flask.Blueprint('integrations', __name__, url_prefix='/integrations')
    new_bp.add_url_rule(
        "/v1/", "list_integrations", list_integrations, methods=["GET"]
    )
    return new_bp


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the integrations registry routes.

    Registers a fresh blueprint on the given app. Called with the
    Flask app itself (not the /auth/v1 blueprint) so the catalog sits
    at the top-level path /integrations/v1 per #688.
    """
    app.register_blueprint(create_blueprint())
