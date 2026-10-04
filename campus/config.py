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
