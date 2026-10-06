"""campus.config

Configuration for Campus base URLs and service mappings.

This module provides environment-aware configuration for service base URLs
using the common.devops environment enums for consistency.

Base URLs are bare service origins (no API path suffix); clients append
the service's own route prefix (e.g. /auth/v1, /audit/v1) themselves.
"""

from campus.common import devops

Url = str

BASE_URLS = {
    "campus.auth": {
        devops.PRODUCTION: "https://auth.campus.nyjc.app",
        devops.STAGING: "https://auth.campus.nyjc.dev",
        devops.DEVELOPMENT: "https://campusauth-development.up.railway.app",
    },
    "campus.api": {
        devops.PRODUCTION: "https://api.campus.nyjc.app",
        devops.STAGING: "https://api.campus.nyjc.dev",
        devops.DEVELOPMENT: "https://campusapi-development.up.railway.app",
    },
    "campus.audit": {
        devops.PRODUCTION: "https://audit.campus.nyjc.app",
        devops.STAGING: "https://audit.campus.nyjc.dev",
        devops.DEVELOPMENT: "https://campusaudit-development.up.railway.app",
    },
}


def get_base_url(app_name: str) -> Url:
    """Get the base URL for a service based on environment.

    ENV is read at call time so processes that set it after import
    (e.g. the test harness) resolve correctly. In the testing
    environment every service resolves to the canonical origin
    (PUBLIC_URL) — the test harness routes /auth, /api and /audit path
    prefixes to the respective in-process Flask apps.

    Args:
        app_name: Service name (e.g., "campus.auth", "campus.api",
            "campus.audit")

    Returns:
        str: Base URL (bare origin) for the service deployment

    Raises:
        ValueError: If no base URL is registered for the service or
            environment
    """
    if app_name not in BASE_URLS:
        raise ValueError(f"No base URL registered for service: {app_name}")
    # Lazy import: url pulls in flask; keep campus.config importable
    # without a web framework.
    from campus.common import env
    from campus.common.utils import url

    app_env = env.get("ENV", devops.DEVELOPMENT)
    if app_env == devops.TESTING:
        return url.canonical_origin()
    url_by_env = BASE_URLS[app_name]
    if app_env not in url_by_env:
        raise ValueError(
            f"No base URL registered for service: {app_name} in environment: {app_env}")
    return url_by_env[app_env]


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

# Public OAuth client ID for CLI/device apps (RFC 6749 Section 2.1)
# Stored in the database as a client with is_public=True and no secret;
# seeded at auth service startup (see campus.auth.resources.client.
# ensure_public_client) so it cannot be missing after a database reset.
PUBLIC_OAUTH_CLIENT_ID = "guest"

# Audit service operator API key (#796). Stored under this fixed id in
# the audit DB's apikeys table; seeded at audit service startup from the
# AUDIT_OPERATOR_API_KEY env var (see campus.audit.resources.apikeys.
# ensure_operator_key). This is the only key class that holds the
# apikeys:* scopes, so key management survives the loss of every other
# key. Rotation: delete this record and restart with a new env value.
AUDIT_OPERATOR_API_KEY_ID = "uid-apikey-operator-0000"

# Scopes seeded on the operator key: full API-key management plus every
# traces scope, so one operator key can administer a deployment (and
# re-seed producer keys) without further bootstrap.
AUDIT_OPERATOR_API_KEY_SCOPES = [
    "apikeys:read",
    "apikeys:write",
    "traces:read",
    "traces:write",
    "traces:search",
]

# Scopes requested by CLI/device apps (RFC 8628). The seeded public
# client's allowlist is exactly this set, and device_authorize defaults
# to it when the caller does not name scopes.
DEFAULT_CLI_SCOPES = ["read", "write"]

SUPPORTED_OAUTH2_GRANT_TYPES = ("code", "device_code")
