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

# Browser login-journey correlation (#803). campus.auth sets this opaque
# cookie at the first browser touch of the login flow (GET /authorize);
# the tracing middleware stamps it into span tags so a login journey can
# be viewed as one group. The final /token hop is server-to-server and
# never carries the cookie, so its handler copies the journey id from the
# auth session into flask.g for the middleware to pick up instead.
JOURNEY_COOKIE = "campus_journey"
JOURNEY_COOKIE_MAX_AGE = 1800  # seconds; ~30 min inactivity TTL

# Action-journey correlation (#828). Set by the journeys middleware
# (campus.audit.middleware.journeys) on page navigations and refreshed
# on every request with an active journey, so one user-initiated action
# episode — page load, its XHRs and form posts, and the server-to-server
# calls they spawn (joined via forwarded X-Journey-ID headers) — groups
# as one journey. Deliberately short and sliding: episodes end on idle
# expiry (or an app's fresh=True journey boundary), never spanning a
# whole session. Distinct from JOURNEY_COOKIE (login flows).
ACTION_JOURNEY_COOKIE = "campus_action_journey"
ACTION_JOURNEY_COOKIE_MAX_AGE = 600  # seconds; ~10 min idle window

# Stable device identity (#825). campus.auth sets this opaque cookie at
# GET /authorize and reuses it on every later login from the same browser
# profile, so login sessions (and their spans) can be attributed to a
# device across re-logins and across client apps. Deliberately a standalone
# cookie, NOT a flask.session key: it is device identity, not session
# state, so /auth/v1/logout's session.clear() must not clear it.
DEVICE_COOKIE = "campus_device"
# 400 days is Chrome's maximum cookie lifetime cap.
DEVICE_COOKIE_MAX_AGE = 400 * 24 * 60 * 60

# Device header (#837): non-browser clients (CLIs, scripts) cannot carry
# the campus_device cookie — they present it on API calls as this header
# instead. The tracing middleware falls back to it after flask.g.device
# and before the cookie. Keep in lockstep with the SDK's
# campus_python.tracing.DEVICE_ID_HEADER (mirrors the X-Journey-ID pair).
DEVICE_ID_HEADER = "X-Campus-Device"

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
