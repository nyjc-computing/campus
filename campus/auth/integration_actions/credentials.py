"""Released-credential loader for integration action proxies (#1221).

Mirrors the broker's integration release flow (routes/broker.py,
`release_integration_token`) invariants without ever emitting the
token: load the target user's stored credential for the integration's
own OAuth client, refresh it silently server-side (invariant B2: the
refresh token never leaves), then fail closed unless the stored grant
covers every scope the action needs (invariant C3b, consent-bounded —
the proxy never mints or widens; a pre-widening grant answers 403 with
`missing_scopes` and the reconnect hint).

The C3a caller-allowlist/cap checks have no analogue here: the
required scopes are server-defined constants per action, not
caller-supplied asks.
"""

from campus.common import schema
from campus.common.errors import api_errors

from .. import integrations
from ..resources import credentials as creds_resource


def get_integration_proxy(integration: integrations.Integration):
    """The integration's base-provider OAuth proxy (lazy import).

    Untyped on purpose, like the broker's _get_integration_proxy: the
    importlib seam carries no stubs, and the proxy's private `_oauth2`
    scheme is the broker-established refresh surface.
    """
    import importlib

    if integration.base_provider != "google":
        raise api_errors.NotFoundError(
            f"Unknown upstream provider {integration.base_provider!r}",
            provider=integration.base_provider,
            integration=integration.slug,
        )
    module = importlib.import_module("campus.auth.oauth_proxy.google")
    return module.get_proxy(integration)


def load_released_credential(
        integration: integrations.Integration,
        user_id: schema.UserID,
        required_scopes: list[str],
) -> tuple[str, str]:
    """Load and silently refresh the target user's stored credential.

    Returns `(access_token, scope_string)` for in-process use by the
    action's REST caller. Raises the broker's error contract:
    404 (no credential / no token, hinting at the connect flow) and
    403 with `missing_scopes` when the stored grant does not cover
    `required_scopes`.
    """
    provider_str = integration.provider
    proxy = get_integration_proxy(integration)
    config = integrations.get_config(integration)

    try:
        credentials = creds_resource[provider_str][user_id].get(
            config.client_id
        )
    except api_errors.NotFoundError:
        raise api_errors.NotFoundError(
            f"No {provider_str} credential for user {user_id}; complete "
            f"the {integration.title} connect flow first (via "
            "the app's integrations page)"
        ) from None
    token = credentials.token
    if token is None:
        raise api_errors.NotFoundError(
            f"No {provider_str} token for user {user_id}"
        )

    # Silent refresh from the stored refresh token so the action always
    # runs on a live access token (invariant B2: the refresh token
    # itself never leaves the process)
    if token.is_expired():
        token = proxy._oauth2.refresh_token(
            token,
            client_id=proxy._CLIENT_ID,
            client_secret=proxy._CLIENT_SECRET,
        )
        creds_resource[provider_str][user_id].update(
            client_id=config.client_id,
            token=token,
        )

    # Consent-bounded (invariant C3b): the stored grant must cover
    # every scope the action needs; the proxy never mints or widens.
    missing_scopes = sorted(set(required_scopes) - set(token.scopes))
    if missing_scopes:
        raise api_errors.ForbiddenError(
            f"The user's {provider_str} grant does not cover the "
            "scopes this action needs; have the user re-consent via "
            "the integration connect flow "
            f"(/auth/v1/{integration.base_provider}/{integration.slug}/authorize)",
            missing_scopes=missing_scopes,
            provider=provider_str,
        )
    return token.id, token.scope
