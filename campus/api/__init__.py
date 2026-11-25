"""campus.api

Web API for Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.api only.
__all__ = ["init_app"]


import collections
import hashlib
import logging
import os
import time
from typing import Any

import campus_python
import flask

from campus.auth.middleware import Authenticator
from campus.common import schema
from campus.common.errors import api_errors

logger = logging.getLogger(__name__)

# Other local imports are intentionally omitted to avoid circular
# dependencies.

# Lazily initialized campus client - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
# Type: ignore because we initialize these in init_app() before first use

campus: campus_python.Campus = None  # type: ignore


def _api_getsecret(name: str) -> str:
    """Get secret from vault for campus.api deployment.

    This function is registered with env.register_getsecret() to provide
    deployment-specific vault access for campus.api.

    Args:
        name: Name of the secret to retrieve

    Returns:
        The secret value from the vault

    Raises:
        OSError: If DEPLOY environment variable is not set
        api_errors.InternalError: If the secret is not found in the vault
    """
    from campus.common import env
    from campus.common.errors import api_errors

    deployment = env.get("DEPLOY")
    if deployment is None:
        raise OSError("Environment variable 'DEPLOY' required")

    import campus_python
    campus_auth = campus_python.Campus().auth
    try:
        return campus_auth.vaults[deployment][name]
    except KeyError:
        raise api_errors.InternalError(
            f"Vault secret '{name}' not found in label '{deployment}'"
        ) from None


# Any 4xx from campus.auth's /root/authenticate endpoint means the
# presented credentials were rejected (unknown client, unknown/expired
# token, bad secret — surfaced by campus_python as various APIError
# subclasses depending on the status campus.auth returned). All of them
# are authentication failures and must surface as 401, never a 500 (#614).
_REJECTED_CREDENTIAL_ERRORS = (
    campus_python.errors.BadRequestError,
    campus_python.errors.AuthenticationError,
    campus_python.errors.AccessDeniedError,
    campus_python.errors.NotFoundError,
    campus_python.errors.ConflictError,
    campus_python.errors.ValidationError,
)

# Introspection cache (#1248): campus tokens are opaque and validated
# server-side, so every campus.api call paid a ~150–240 ms
# /root/authenticate round trip — the 2026-11-24 classroom journey
# investigation clocked a 10-span submit journey introspecting the same
# bearer 8–11 times. Cache authenticate results per credential digest
# for a short TTL. The tradeoff is explicit: a token revoked mid-TTL
# stays accepted on this worker until its entry expires; set
# AUTH_INTROSPECTION_TTL_SECONDS=0 to disable the cache entirely.
_INTROSPECTION_TTL_SECONDS = 30.0
_INTROSPECTION_CACHE_MAX = 4096
_introspection_cache: "collections.OrderedDict[str, tuple[float, dict[str, Any]]]" = (
    collections.OrderedDict()
)


def _introspection_ttl() -> float:
    """Configured cache TTL in seconds (0 = cache disabled)."""
    raw = os.environ.get("AUTH_INTROSPECTION_TTL_SECONDS", "")
    try:
        return max(float(raw), 0.0) if raw else _INTROSPECTION_TTL_SECONDS
    except ValueError:
        return _INTROSPECTION_TTL_SECONDS


def _credential_key(kind: str, credential: str) -> str:
    # Digest, never the raw credential: nothing here is long-lived, but
    # a dump of this dict must not carry bearer tokens or secrets.
    return kind + ":" + hashlib.sha256(credential.encode("utf-8")).hexdigest()


def _cached_auth_result(key: str) -> dict[str, Any] | None:
    """Live cached authenticate result for this credential, or None."""
    ttl = _introspection_ttl()
    if ttl <= 0:
        return None
    entry = _introspection_cache.get(key)
    if entry is None:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > ttl:
        _introspection_cache.pop(key, None)
        return None
    _introspection_cache.move_to_end(key)
    # Copy: the caller owns its instance (it lands on flask.g).
    return dict(result)


def _remember_auth_result(key: str, result: dict[str, Any]) -> dict[str, Any]:
    """Cache and return an authenticate result (bounded LRU)."""
    if _introspection_ttl() > 0:
        _introspection_cache[key] = (time.monotonic(), result)
        _introspection_cache.move_to_end(key)
        while len(_introspection_cache) > _INTROSPECTION_CACHE_MAX:
            _introspection_cache.popitem(last=False)
    return dict(result)


def basic_authenticate(client_id: str, client_secret: str) -> dict[str, Any]:
    """Authenticate using HTTP Basic Authentication.

    Results are cached per credential for the introspection TTL
    (#1248) — a revoke takes up to one TTL to bite on this worker.
    """
    key = _credential_key("basic", f"{client_id}:{client_secret}")
    cached = _cached_auth_result(key)
    if cached is not None:
        return cached
    try:
        auth_result = campus.auth.root.authenticate(
            client_id=schema.CampusID(client_id),
            client_secret=client_secret
        )
    except _REJECTED_CREDENTIAL_ERRORS:
        raise api_errors.UnauthorizedError(
            "Invalid client credentials"
        ) from None
    return _remember_auth_result(key, {
        "client": auth_result["client"],
        "user": None,
    })

def bearer_authenticate(token: str) -> dict[str, Any]:
    """Authenticate using HTTP Bearer Authentication.

    Results are cached per token for the introspection TTL (#1248):
    a multi-span journey introspects the same bearer once per TTL
    instead of once per call; a revoke takes up to one TTL to bite
    on this worker.
    """
    key = _credential_key("bearer", token)
    cached = _cached_auth_result(key)
    if cached is not None:
        return cached
    try:
        auth_result = campus.auth.root.authenticate(token=token)
    except _REJECTED_CREDENTIAL_ERRORS:
        raise api_errors.UnauthorizedError(
            "Invalid access token"
        ) from None
    return _remember_auth_result(key, {
        "client": auth_result["client"],
        "user": auth_result.get("user"),
        # the token's granted scopes (#1183): the Authenticator
        # hydrates flask.g.current_scopes from this so route gates can
        # enforce the capability leg of the two-leg model (#865)
        "scopes": auth_result.get("scopes", []),
    })

# Create authenticator using campus_python
campus_authenticator = Authenticator(
    basic_authenticator=basic_authenticate,
    bearer_authenticator=bearer_authenticate,
)


def _init_api_tables() -> None:
    """Initialize api storage tables and the circle bootstrap, logging loudly on failure.

    CREATE TABLE IF NOT EXISTS per table (idempotent), so a fresh or
    reset deployment self-heals on the next deploy. Document-backed
    resources (assignments, circles, submissions, ...) auto-create
    their collections and need no such call; the circles collection is
    additionally seeded with the access-control bootstrap (root/admin
    sentinels and the per-resource role circles,
    docs/circles-access-control.md). The production guard +
    loud-failure convention lives in campus.bootstrap (#1103):
    initialization is skipped in production, where schema is managed
    by migrations/scripts.
    """
    from campus import bootstrap

    def _init_emailotp_table() -> None:
        from .resources.emailotp import EmailOTPResource
        EmailOTPResource.init_storage()

    bootstrap.run_init_storage(
        _init_emailotp_table,
        what="the email OTP table (OTP request/verify depends on it)",
        recovery="python scripts/init_storage.py --service api",
    )

    def _init_bookings_table() -> None:
        # The venue bookings table is a storage table (not a
        # self-creating collection); without it, the bookings routes
        # cannot create or read bookings (campus#1217).
        from .resources.booking import init_storage as init_bookings

        init_bookings()

    bootstrap.run_init_storage(
        _init_bookings_table,
        what="the venue bookings table (the bookings routes depend "
             "on it, campus#1217)",
        recovery="python scripts/init_storage.py --service api (or "
                 "migrations/013_create_venue_bookings_table.py)",
    )

    def _init_timetable_table() -> None:
        # The timetable members table is a storage table (not a
        # self-creating collection); without it, creating a
        # timetable with lessongroup members fails.
        from .resources.timetable import TimetablesResource
        TimetablesResource.init_storage()

    bootstrap.run_init_storage(
        _init_timetable_table,
        what="the timetable members table (timetable creation with "
             "lessongroup members depends on it)",
        recovery="python scripts/init_storage.py --service api",
    )

    def _init_calendar_table() -> None:
        # The school calendar is a storage table (not a
        # self-creating collection); without it, the calendar
        # routes and the timetable editor cannot read or write
        # day-codes.
        from .resources.calendar import CalendarResource
        CalendarResource.init_storage()

    bootstrap.run_init_storage(
        _init_calendar_table,
        what="the school calendar table (the calendar routes and the "
             "timetable editor depend on it)",
        recovery="python scripts/init_storage.py --service api (or "
                 "migrations/011_create_calendar_table.py)",
    )

    def _init_circles_bootstrap() -> None:
        from .resources.circle import CirclesResource
        CirclesResource.init_storage()

    bootstrap.run_init_storage(
        _init_circles_bootstrap,
        what="the circle access-control bootstrap (resource/role "
             "circles depend on it, docs/circles-access-control.md)",
        recovery="python scripts/init_storage.py --service api",
    )


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    from campus.common import env

    # Register deployment-specific getsecret function
    env.register_getsecret(_api_getsecret)

    # Ensure the SQL-backed api storage tables exist before first use.
    _init_api_tables()

    # Initialize campus client after test fixtures have set up the vault
    global campus
    campus = campus_python.Campus()

    # Propagate trace context on authenticate calls to campus.auth so the
    # auth span ingests as a child of the api request's span (#794).
    # In tests the SDK is patched to TestCampusRequest, which has no
    # requests.Session; those requests get headers from tests.flask_test.
    from campus.flask_campus.audit import tracing

    session = getattr(campus.auth.client, "_session", None)
    if session is not None:
        tracing.instrument_requests_session(session)

    from . import routes

    # Organise API routes under api blueprint
    bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')
    routes.assignments.init_app(bp)
    routes.bookings.init_app(bp)
    routes.calendar.init_app(bp)
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.files.init_app(bp)
    routes.hostedapps.init_app(bp)
    routes.subjcombi.init_app(bp)
    routes.submissions.init_app(bp)
    routes.timetable.init_app(bp)
    routes.users.init_app(bp)
    routes.venues.init_app(bp)

    # Apply authentication to all API routes
    bp.before_request(campus_authenticator.authenticate)

    # Migration management routes (#1169): the campus-admin Migrations
    # view drives plan/apply/abort/rollback per service. Shared
    # blueprint from migrations/routes.py, inside the authenticated api
    # namespace. The grant store lives only in campus.auth's database,
    # so the gate settles the designation leg over the mesh (#1168
    # service leg: GET /grants/check with THIS deployment's client
    # credentials, allowlisted by AUTH_GRANT_CHECK_CLIENT_IDS) —
    # reusing the shared SDK client so the check rides the traced
    # session (#794). Mutations emit yapper events stamped with the
    # acting user.
    import migrations.routes as migration_routes

    _migrations_yapper = None

    def _migrations_emit(event: str, data: dict) -> None:
        nonlocal _migrations_yapper
        import campus.yapper

        if _migrations_yapper is None:
            _migrations_yapper = campus.yapper.create()
        user = getattr(flask.g, "current_user", None) or {}
        _migrations_yapper.emit(event, {
            **data,
            "acting_user": str(user.get("id") or "") if isinstance(
                user, dict) else str(getattr(user, "id", "")),
        })

    migration_routes.init_app(
        bp,
        service_db="api",
        gate=migration_routes.make_grant_check_gate(
            "api",
            client_getter=lambda: campus.auth,
            principal_description="Client principals",
        ),
        emit=_migrations_emit,
    )

    # Action journeys (#828), adopt-only: campus.api serves no browser
    # pages, so there is nothing to mint on — adopting SDK-forwarded
    # X-Journey-ID headers lets api spans join the caller's action
    # journey (e.g. a classroom submit and its assignment POST).
    from campus.flask_campus.audit import init_journeys
    init_journeys(app, mint_on_navigation=False)

    app.register_blueprint(bp)

    if isinstance(app, flask.Flask):
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY")

# v0.2.1 campus-common wheel switch deployed from this commit (#988).


# Service-level OpenAPI info (campus#1029): consumed by
# campus.flask_campus.openapi; migrated from the former
# hand-maintained docs/openapi.yaml.
OPENAPI_INFO = {
    "title": "Campus API",
    "description": """Campus API for managing educational resources.

## Error Responses

All error responses follow a consistent envelope format. See the `ErrorEnvelope` schema for details.

## Error Codes

Common error codes:
- `INVALID_REQUEST` (400): Malformed or invalid request
- `UNAUTHORIZED` (401): Missing or invalid authentication
- `FORBIDDEN` (403): Insufficient permissions
- `NOT_FOUND` (404): Resource not found
- `VALIDATION_FAILED` (422): Request validation failed with field-level errors
- `CONFLICT` (409): Resource state conflict
- `INTERNAL_ERROR` (500): Unexpected server error
- `SERVICE_UNAVAILABLE` (503): Required dependency is down; retry later
""",
}
