"""campus.auth.routes.connections

Connection inventory + disconnect routes (#733 Phase 2, design §2.7).

The connections surface is the user-facing view of the upstream
credentials Campus custodies: which integrations (and identity
providers) a user has granted, and an explicit way to revoke that
grant. It is metadata-only — no token value is ever accepted or
returned here (invariant C2). Token release stays broker-only (C1)
and the credentials HTTP API stays campus-only (B1).

Audit: campus.integrations.disconnect (no token values).
"""

__all__ = [
    "create_blueprint",
]

import flask

import campus.model
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import get_yapper, integrations
from ..resources import credentials as creds_resource

# Create blueprint for connection routes
bp = flask.Blueprint('connections', __name__, url_prefix='/connections')


def _resolve_target_user() -> schema.UserID:
    """Resolve the user a connections call acts on (design §2.7).

    A campus bearer token is self-service: it acts for its own user,
    and any user_id parameter is ignored. Basic (client-credentials)
    auth carries no user, so it must name one explicitly via the
    user_id query parameter — the delegated form server-mode apps
    (campus-profile) use. Fail closed when a basic call names no one.
    """
    user = flask.g.current_user
    if user:
        return schema.UserID(user["id"])
    user_id = flask.request.args.get("user_id")
    if not user_id:
        raise api_errors.InvalidRequestError(
            "user_id is required for delegated (basic auth) "
            "connections access"
        )
    return schema.UserID(user_id)


def _reject_campus_provider(provider: str) -> None:
    """Disconnecting campus tokens is logout, not a connection change.

    Campus tokens are revoked via /oauth/revoke (RFC 7009); the
    connections surface only manages upstream grants (invariant C5).
    """
    if provider == "campus":
        raise api_errors.ForbiddenError(
            "Campus tokens are revoked via POST /oauth/revoke, not the "
            "connections API (docs/auth-token-invariants.md C5)"
        )


def _connection_payload(
        credentials: campus.model.UserCredentials,
) -> dict:
    """Shape one connection entry (design §2.7). Metadata only."""
    token = credentials.token
    try:
        integration = integrations.resolve(credentials.provider).slug
    except api_errors.NotFoundError:
        integration = None
    return {
        "provider": credentials.provider,
        "integration": integration,
        "scopes": list(token.scopes) if token else [],
        "connected_at": credentials.created_at,
        "expires_at": token.expires_at if token else None,
    }


def _emit_disconnect(
        client_id: str,
        user_id: schema.UserID,
        deleted: list[campus.model.UserCredentials],
        integration: str | None = None,
) -> None:
    """Emit the disconnect audit event (invariant C4-style). Never
    logs token values."""
    scopes: list[str] = []
    for credentials in deleted:
        if credentials.token:
            for scope in credentials.token.scopes:
                if scope not in scopes:
                    scopes.append(scope)
    payload: dict = {
        "client_id": client_id,
        "user_id": str(user_id),
        "provider": deleted[0].provider,
        "scopes": scopes,
    }
    if integration is not None:
        payload["integration"] = integration
    get_yapper().emit('campus.integrations.disconnect', payload)


@bp.get("/")
def list_connections() -> flask_campus.JsonResponse:
    """List the user's upstream connections.

    GET /connections/
    Auth: campus bearer token (self) or basic auth + user_id
    (delegate). Under bearer auth the inventory is always the bearer's
    own.
    Returns: {
        "connections": [
            {
                "provider": "google.classroom",
                "integration": "classroom",  (null for identity providers)
                "scopes": ["..."],
                "connected_at": "<UTC datetime>",
                "expires_at": "<UTC datetime> | null"
            }
        ]
    }

    Campus login tokens are not connections (C5) and are not listed;
    no token value is ever returned (C2).
    """
    target_user = _resolve_target_user()
    connections = [
        _connection_payload(credentials)
        for credentials in creds_resource.list_connections(target_user)
    ]
    return {"connections": connections}, 200


@bp.delete("/<provider>/")
def disconnect_provider(provider: str) -> flask_campus.JsonResponse:
    """Disconnect the user's credentials for a base provider.

    DELETE /connections/{provider}/   e.g. /connections/google/
    Auth: campus bearer token (self) or basic auth + user_id
    (delegate).
    Returns: {} with 200

    Deletes every stored credential row for (provider, user) together
    with its token record. The next login or connect re-establishes
    the grant; 404 means there was nothing to disconnect.
    """
    target_user = _resolve_target_user()
    _reject_campus_provider(provider)
    # Namespaced providers disconnect via the integration route only,
    # mirroring the broker's release grammar (#733).
    try:
        namespaced = integrations.resolve(provider)
    except api_errors.NotFoundError:
        pass
    else:
        raise api_errors.NotFoundError(
            f"Disconnect {provider} via the integration route "
            f"(/auth/v1/connections/{namespaced.base_provider}/"
            f"{namespaced.slug}/)",
            provider=provider,
            integration=namespaced.slug,
        )
    deleted = creds_resource.disconnect(provider, target_user)
    if not deleted:
        raise api_errors.NotFoundError(
            f"No {provider} connection for user {target_user}"
        )
    _emit_disconnect(str(flask.g.current_client.id), target_user, deleted)
    return {}, 200


@bp.delete("/<provider>/<integration>/")
def disconnect_integration(
        provider: str,
        integration: str,
) -> flask_campus.JsonResponse:
    """Disconnect the user's credentials for an integration.

    DELETE /connections/{provider}/{integration}/
    e.g. /connections/google/classroom/
    Auth: campus bearer token (self) or basic auth + user_id
    (delegate).
    Returns: {} with 200

    Deletes every stored credential row for the namespaced provider
    together with its token records, and emits
    campus.integrations.disconnect (no token values).
    """
    target_user = _resolve_target_user()
    _reject_campus_provider(provider)
    campus_integration = integrations.get(integration)
    if campus_integration.base_provider != provider:
        raise api_errors.NotFoundError(
            f"Unknown upstream provider {provider!r} for integration "
            f"{integration!r}",
            provider=provider,
            integration=integration,
        )
    deleted = creds_resource.disconnect(
        campus_integration.provider, target_user
    )
    if not deleted:
        raise api_errors.NotFoundError(
            f"No {campus_integration.provider} connection for user "
            f"{target_user}"
        )
    _emit_disconnect(
        str(flask.g.current_client.id),
        target_user,
        deleted,
        integration=campus_integration.slug,
    )
    return {}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('connections', __name__, url_prefix='/connections')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "list_connections", list_connections, methods=["GET"])
    new_bp.add_url_rule(
        "/<provider>/", "disconnect_provider", disconnect_provider,
        methods=["DELETE"]
    )
    new_bp.add_url_rule(
        "/<provider>/<integration>/", "disconnect_integration",
        disconnect_integration,
        methods=["DELETE"]
    )

    return new_bp
