"""campus.config

Configuration for Campus service URLs and service-policy constants.

Service URL resolution is owned by campus.common.services (campus-common):
one resolver serves the suite, the campus_python SDK, and downstream
apps. The environment is the source of truth — per-service overrides
(CAMPUS_AUTH_URL / AUTH_URL / ...) over a gateway base-URL fallback
(CAMPUS_BASE_URL / BASE_URL); Campus ships no baked-in deployment
topology. The remaining constants are service policy shared by the auth
and audit services (expiries, journey cookie names, CLI scopes,
operator key seeding).
"""

from campus.common import services

Url = str


def get_base_url(app_name: str) -> Url:
    """Get the base URL for a service based on environment.

    Delegates to campus.common.services.get_base_url. ENV is read at
    call time so processes that set it after import (e.g. the test
    harness) resolve correctly. In the testing environment every
    service resolves to the canonical origin (PUBLIC_URL) — the test
    harness routes /auth, /api and /audit path prefixes to the
    respective in-process Flask apps — and a deployment resolving its
    own name (DEPLOY) does the same, so a service never routes to
    itself through its public URL.

    Args:
        app_name: Service name (e.g., "campus.auth", "campus.api",
            "campus.audit")

    Returns:
        str: Base URL (bare origin) for the service deployment

    Raises:
        ValueError: If no base URL is configured for the service, or a
            configured override/base URL is not a bare origin (see
            campus.common.services for the chain)
    """
    return services.get_base_url(app_name)


DEFAULT_LOGIN_EXPIRY_DAYS = 30
DEFAULT_OAUTH_EXPIRY_MINUTES = 10
DEFAULT_TOKEN_EXPIRY_DAYS = 7
DEFAULT_DEVICE_CODE_EXPIRY_SECONDS = 600  # 10 minutes
DEFAULT_DEVICE_CODE_POLL_INTERVAL = 5  # seconds

# Wire-protocol constants (journey/device cookie names + TTLs, the
# X-Campus-Device / X-Journey-* / X-Request-* header names) moved to
# campus.common.protocol (campus#1041) — they are shared vocabulary
# with the flask-campus consumer layer and the SDK, not suite-internal
# configuration. This module keeps only suite-internal settings.

# Distinct Flask session cookie names per deployment. campus.auth and
# campus.audit both keep browser state in flask.session, each signed with
# its own vault SECRET_KEY. On separate hostnames the cookies never meet;
# behind one hostname (path-dispatched reverse proxy) they share the
# browser's cookie jar, so same-named cookies clobber each other and each
# service rejects the other's signature. Unlisted deployments (campus.api
# keeps no browser session) keep Flask's default 'session' cookie.
# Correlation cookies (campus_journey, campus_device,
# campus_action_journey) are already uniquely named and stay host-wide
# on purpose. Applied in deploy.create_app.
SESSION_COOKIE_NAMES = {
    "campus.auth": "campus_auth_session",
    "campus.audit": "campus_audit_session",
}

# Public OAuth client ID for CLI/device apps (RFC 6749 Section 2.1)
# Stored in the database as a client with is_public=True and no secret;
# seeded at auth service startup (see campus.auth.resources.client.
# ensure_public_client) so it cannot be missing after a database reset.
PUBLIC_OAUTH_CLIENT_ID = "guest"

# Audit service operator API key (#796). Stored under this fixed id in
# the audit DB's apikeys table; seeded at audit service startup from the
# AUDIT_OPERATOR_API_KEY env var (see campus.audit.resources.apikeys.
# ensure_operator_key). The seed breaks the key-management
# chicken-and-egg: the apikeys routes are apikeys:write-gated, so no key
# could ever be minted if none existed. Rotation: delete this record and
# restart with a new env value.
AUDIT_OPERATOR_API_KEY_ID = "uid-apikey-operator-0000"

# Scopes seeded on the operator key: full API-key management plus trace
# ingest — no trace-READ scopes. The operator bootstraps keys and
# writes traces; reading traces is a human activity, done through the
# web UI / CLI with a person's own credentials (superadmin OAuth or a
# traces:read key), never the deployment's service credential
# (2026-10-21 ruling).
AUDIT_OPERATOR_API_KEY_SCOPES = [
    "apikeys:read",
    "apikeys:write",
    "traces:write",
]

# Scopes requested by CLI/device apps (RFC 8628). The seeded public
# client's allowlist is exactly this set, and device_authorize defaults
# to it when the caller does not name scopes.
DEFAULT_CLI_SCOPES = ["read", "write"]

SUPPORTED_OAUTH2_GRANT_TYPES = ("code", "device_code")
