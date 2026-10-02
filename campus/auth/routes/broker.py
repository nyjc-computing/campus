"""campus.auth.routes.broker

Token bridge: releases upstream provider access tokens to authorized
confidential clients on behalf of the authenticated user.

Campus is the sole custodian of upstream credentials (Google, GitHub,
Discord): apps in the Campus ecosystem must not store non-campus
tokens. This endpoint is the ONLY sanctioned release path. Upstream
refresh tokens never leave Campus — responses carry the short-lived
access token, its expiry, and its scope, nothing else.

Invariants: docs/auth-token-invariants.md B1-B5, C1-C5.
"""

import logging

import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors, auth_errors

from .. import get_yapper, integrations
from .. import scopes as campus_scopes
from ..resources import credentials as creds_resource
from ..resources import vault as vault_resource

logger = logging.getLogger(__name__)

# Create blueprint for token bridge routes
bp = flask.Blueprint('broker', __name__, url_prefix='/broker')

# Google identity scopes: the base set a plain campus login grants
# (email, profile, in both OAuth short and URL forms). min_scopes
# beyond these on the identity broker route are integration asks that
# belong on the per-integration broker routes (#733 Phase 1).
_GOOGLE_IDENTITY_SCOPES = {
    "email",
    "profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
}

# Providers with an OAuth proxy, mapped to their proxy module.
# Imported lazily in _get_proxy: proxy modules import auth resources.
_PROXY_MODULES = {
    "discord": "campus.auth.oauth_proxy.discord",
    "github": "campus.auth.oauth_proxy.github",
    "google": "campus.auth.oauth_proxy.google",
}


def _get_proxy(provider: str):
    """Return the OAuth proxy instance for an upstream provider."""
    if provider not in _PROXY_MODULES:
        raise api_errors.NotFoundError(
            f"Unknown upstream provider {provider!r}",
            provider=provider,
        )
    import importlib
    module = importlib.import_module(_PROXY_MODULES[provider])
    return module.get_proxy()


def _get_integration_proxy(integration: integrations.Integration):
    """Return the OAuth proxy for an integration's base provider."""
    if integration.base_provider not in _PROXY_MODULES:
        raise api_errors.NotFoundError(
            f"Unknown upstream provider {integration.base_provider!r}",
            provider=integration.base_provider,
            integration=integration.slug,
        )
    import importlib
    module = importlib.import_module(_PROXY_MODULES[integration.base_provider])
    return module.get_proxy(integration)


def _authorize_bridge_call() -> tuple[str, schema.UserID]:
    """Enforce the token bridge access guards (invariant C1).

    The call must be bearer-authenticated (a user context), and the
    client must be confidential AND flagged for bridge access.
    Fail-closed: any missing condition denies.

    Returns:
        (client_id, user_id) of the authenticated caller.
    """
    client = flask.g.current_client
    user = flask.g.current_user
    if not user:
        # Basic (client-credentials) auth carries no user to release for
        raise api_errors.ForbiddenError(
            "Token bridge requires a campus bearer token bound to a user"
        )
    if client is None or client.is_public:
        # Public clients (SPAs, CLIs) must never receive upstream tokens
        raise api_errors.ForbiddenError(
            "Public clients are not eligible for token bridge access"
        )
    if not client.token_bridge:
        raise api_errors.ForbiddenError(
            "Client is not flagged for token bridge access"
        )
    return str(client.id), schema.UserID(user["id"])


def _deny(
        client_id: str,
        user_id: schema.UserID,
        provider: str,
        reason: str,
        **details,
) -> None:
    """Emit a denial audit event (invariant C4). Never logs tokens."""
    get_yapper().emit('campus.broker.deny', {
        "client_id": client_id,
        "user_id": str(user_id),
        "provider": provider,
        "reason": reason,
        **details,
    })


@bp.post("/<provider>/")
@flask_campus.unpack_request
def release_upstream_token(
        provider: str,
        min_scopes: list[str] | None = None,
) -> flask_campus.JsonResponse:
    """Release the user's upstream access token for a provider.

    POST /broker/{provider}
    Auth: campus Bearer token (the user), issued to a confidential
    client flagged for bridge access.
    Body: {
        "min_scopes": ["https://www.googleapis.com/auth/classroom.rosters"]
        # Optional: scopes the caller requires. Denied unless the user's
        # upstream grant covers them AND the client's upstream_scopes
        # allowlist permits them.
    }
    Returns: {
        "provider": "google",
        "user_id": "user@nyjc.edu.sg",
        "access_token": "<upstream access token>",
        "token_type": "Bearer",
        "expires_in": 1234,
        "scope": "email profile https://..."
    }

    The refresh token is never included: Campus refreshes silently via
    its stored credential and remains the sole custodian. Tokens are
    released for in-memory use until expiry only — downstream apps must
    not persist them (invariant D1).
    """
    client_id, user_id = _authorize_bridge_call()
    requested_scopes = campus_scopes.parse(min_scopes)

    # Deprecation telemetry (pre-implementation for #733): non-identity
    # min_scopes on the identity route are integration asks that should
    # move to the per-integration broker routes once they exist. These
    # events are the who-still-uses-old-paths inventory that gates that
    # retirement; denied calls are additionally counted by campus.broker.deny.
    if provider == "google" and not set(requested_scopes) <= _GOOGLE_IDENTITY_SCOPES:
        logger.warning(
            "Deprecated non-identity min_scopes on /broker/google/ (client %s): %s",
            client_id,
            requested_scopes,
        )
        get_yapper().emit('campus.auth.deprecated_call', {
            "endpoint": "broker.google",
            "client_id": client_id,
            "user_id": str(user_id),
            "param": "min_scopes",
            "requested_scopes": requested_scopes,
        })

    # C3a: the caller may only ask for scopes its registration allows
    try:
        campus_scopes.validate_upstream_for_client(
            flask.g.current_client.upstream_scopes,
            provider,
            requested_scopes,
        )
    except auth_errors.InvalidScopeError:
        _deny(
            client_id, user_id, provider,
            reason="min_scopes exceed the client's upstream_scopes allowlist",
            requested_scopes=requested_scopes,
        )
        raise

    proxy = _get_proxy(provider)
    try:
        upstream_client_id = vault_resource[provider]["CLIENT_ID"]
    except KeyError:
        raise api_errors.NotFoundError(
            f"No upstream client configured for provider {provider!r}",
            provider=provider,
        ) from None

    try:
        credentials = creds_resource[provider][user_id].get(
            upstream_client_id
        )
    except api_errors.NotFoundError:
        _deny(
            client_id, user_id, provider,
            reason="no upstream credential for user",
        )
        raise api_errors.NotFoundError(
            f"No {provider} credential for user {user_id}; complete a "
            "login or upstream consent flow first"
        ) from None
    token = credentials.token
    if token is None:
        _deny(
            client_id, user_id, provider,
            reason="upstream credential has no token",
        )
        raise api_errors.NotFoundError(
            f"No {provider} token for user {user_id}"
        )

    # Silent refresh: Campus refreshes from its stored refresh token so
    # callers only ever see a live access token (invariant B2: the
    # refresh token itself never leaves)
    if token.is_expired():
        token = proxy._oauth2.refresh_token(
            token,
            client_id=proxy._CLIENT_ID,
            client_secret=proxy._CLIENT_SECRET,
        )
        creds_resource[provider][user_id].update(
            client_id=upstream_client_id,
            token=token,
        )

    # C3b: the stored grant must cover the requested minimum
    missing_scopes = sorted(
        set(requested_scopes) - set(token.scopes)
    )
    if missing_scopes:
        _deny(
            client_id, user_id, provider,
            reason="upstream grant does not cover min_scopes",
            missing_scopes=missing_scopes,
        )
        raise api_errors.ForbiddenError(
            f"The user's {provider} grant does not cover the requested "
            "scopes; re-consent via /auth/v1/authorize with "
            "upstream_scope set to the missing scopes",
            missing_scopes=missing_scopes,
            provider=provider,
        )

    get_yapper().emit('campus.broker.release', {
        "client_id": client_id,
        "user_id": str(user_id),
        "provider": provider,
        "requested_scopes": requested_scopes,
        "scope_count": len(token.scopes),
    })

    # C2: minimal exposure — build the response explicitly; the token
    # resource's refresh_token and provider_fields are never emitted
    expires_in = max(
        0,
        int(token.expires_at.to_timestamp()
            - schema.DateTime.utcnow().to_timestamp()),
    )
    return {
        "provider": provider,
        "user_id": str(user_id),
        "access_token": token.id,
        "token_type": token.token_type,
        "expires_in": expires_in,
        "scope": token.scope,
    }, 200


@bp.post("/<provider>/<integration>/")
@flask_campus.unpack_request
def release_integration_token(
        provider: str,
        integration: str,
        min_scopes: list[str] | None = None,
) -> flask_campus.JsonResponse:
    """Release the user's upstream access token for an integration.

    POST /broker/{provider}/{integration}
    e.g. POST /broker/google/classroom/
    Auth: campus Bearer token (the user), issued to a confidential
    client flagged for bridge access (same guards as the identity
    route, invariant C1).
    Body: {"min_scopes": ["..."]}  (optional)
    Returns: same shape as the identity route, with the namespaced
    provider string (e.g. "google.classroom"); no refresh token, ever
    (invariant B2).

    Integration-specific rules (#733, design §2.4-§2.5):
    - The caller's upstream_scopes must carry a NON-EMPTY entry for the
      namespaced provider even when min_scopes is omitted: an
      integration token inherently carries integration scopes, so an
      absent entry means no access at all (fail-closed).
    - min_scopes are additionally capped by the integration's vault
      SCOPES set; asking beyond it is a configuration error.
    - A missing user credential is a 404 whose hint points at the
      connect flow, not at the deprecated upstream_scope login path.
    """
    client_id, user_id = _authorize_bridge_call()
    campus_integration = integrations.get(integration)
    if campus_integration.base_provider != provider:
        raise api_errors.NotFoundError(
            f"Unknown upstream provider {provider!r} for integration "
            f"{integration!r}",
            provider=provider,
            integration=integration,
        )
    provider_str = campus_integration.provider
    requested_scopes = campus_scopes.parse(min_scopes)

    # Fails closed (404) when the integration's vault label has no
    # upstream OAuth client.
    integration_proxy = _get_integration_proxy(campus_integration)
    config = integrations.get_config(campus_integration)

    # Amended C3a rule for integrations (#733): a namespaced provider
    # has no "base scopes" to fall back on, so an absent or empty
    # allowlist entry denies even a min_scopes-less release.
    allowed = flask.g.current_client.upstream_scopes.get(provider_str, [])
    if not allowed:
        _deny(
            client_id, user_id, provider_str,
            integration=campus_integration.slug,
            reason="client has no upstream_scopes entry for this integration",
            requested_scopes=requested_scopes,
        )
        raise auth_errors.InvalidScopeError(
            f"Client is not allowed to request {provider_str} scopes; "
            "add a non-empty upstream_scopes entry for the integration",
            provider=provider_str,
        )

    # C3a: the caller may only ask for scopes its registration allows
    try:
        campus_scopes.validate_upstream_for_client(
            flask.g.current_client.upstream_scopes,
            provider_str,
            requested_scopes,
        )
    except auth_errors.InvalidScopeError:
        _deny(
            client_id, user_id, provider_str,
            integration=campus_integration.slug,
            reason="min_scopes exceed the client's upstream_scopes allowlist",
            requested_scopes=requested_scopes,
        )
        raise

    # The vault SCOPES set is the integration's hard cap, independent
    # of any client allowlist (design §2.5): a scope beyond it can never
    # be granted by this Google client, so asking for it is a
    # configuration bug, not a re-consent situation.
    beyond_cap = [
        scope for scope in requested_scopes
        if scope not in set(integration_proxy.scopes)
    ]
    if beyond_cap:
        _deny(
            client_id, user_id, provider_str,
            integration=campus_integration.slug,
            reason="min_scopes exceed the integration's vault SCOPES cap",
            requested_scopes=requested_scopes,
        )
        raise auth_errors.InvalidScopeError(
            f"Requested scopes exceed the {provider_str} integration's "
            f"configured scope cap: {', '.join(beyond_cap)}",
            provider=provider_str,
            disallowed_scopes=beyond_cap,
        )

    try:
        credentials = creds_resource[provider_str][user_id].get(
            config.client_id
        )
    except api_errors.NotFoundError:
        _deny(
            client_id, user_id, provider_str,
            integration=campus_integration.slug,
            reason="no upstream credential for user",
        )
        raise api_errors.NotFoundError(
            f"No {provider_str} credential for user {user_id}; complete "
            f"the {campus_integration.title} connect flow first (via "
            "the app's integrations page)"
        ) from None
    token = credentials.token
    if token is None:
        _deny(
            client_id, user_id, provider_str,
            integration=campus_integration.slug,
            reason="upstream credential has no token",
        )
        raise api_errors.NotFoundError(
            f"No {provider_str} token for user {user_id}"
        )

    # Silent refresh: Campus refreshes from its stored refresh token so
    # callers only ever see a live access token (invariant B2: the
    # refresh token itself never leaves)
    if token.is_expired():
        token = integration_proxy._oauth2.refresh_token(
            token,
            client_id=integration_proxy._CLIENT_ID,
            client_secret=integration_proxy._CLIENT_SECRET,
        )
        creds_resource[provider_str][user_id].update(
            client_id=config.client_id,
            token=token,
        )

    # C3b: the stored grant must cover the requested minimum
    missing_scopes = sorted(
        set(requested_scopes) - set(token.scopes)
    )
    if missing_scopes:
        _deny(
            client_id, user_id, provider_str,
            integration=campus_integration.slug,
            reason="upstream grant does not cover min_scopes",
            missing_scopes=missing_scopes,
        )
        raise api_errors.ForbiddenError(
            f"The user's {provider_str} grant does not cover the "
            "requested scopes; re-consent via the integration connect "
            f"flow (/auth/v1/{provider}/{campus_integration.slug}/authorize)",
            missing_scopes=missing_scopes,
            provider=provider_str,
        )

    get_yapper().emit('campus.broker.release', {
        "client_id": client_id,
        "user_id": str(user_id),
        "provider": provider_str,
        "integration": campus_integration.slug,
        "requested_scopes": requested_scopes,
        "scope_count": len(token.scopes),
    })

    # C2: minimal exposure — build the response explicitly; the token
    # resource's refresh_token and provider_fields are never emitted
    expires_in = max(
        0,
        int(token.expires_at.to_timestamp()
            - schema.DateTime.utcnow().to_timestamp()),
    )
    return {
        "provider": provider_str,
        "user_id": str(user_id),
        "access_token": token.id,
        "token_type": token.token_type,
        "expires_in": expires_in,
        "scope": token.scope,
    }, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('broker', __name__, url_prefix='/broker')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule(
        "/<provider>/", "release_upstream_token", release_upstream_token,
        methods=["POST"]
    )
    new_bp.add_url_rule(
        "/<provider>/<integration>/", "release_integration_token",
        release_integration_token,
        methods=["POST"]
    )

    return new_bp
