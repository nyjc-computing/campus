"""campus.audit.web.keys

Key-management page for the Audit Web UI (#927).

Reading traces and managing keys are separate capabilities
(docs/web-ui-requirements.md §5.2): a session that may read traces
cannot mint keys, and a session that may mint keys is not automatically
allowed to read traces. This blueprint is gated on can_manage_keys().

Everything here acts as the *session*, never as the deployment's
operator key: the resources layer is called in-process, so no key
material passes through the server, and each mutation is attributed to
the session that made it — the key id for an API-key session, the
campus.auth account for a superadmin session (see current_actor()).

The plaintext of a minted or rotated key is shown once, in the response
that created it, and is never stored: not in the session, not in the
audit trail, not in a log line. Every response from this blueprint is
Cache-Control: no-store.
"""

__all__ = ["create_blueprint"]

import hmac
import logging
import secrets
import typing
from datetime import datetime

import flask
import werkzeug

from campus.common import schema
from campus.common.errors import api_errors

from ..resources import apikeys as apikeys_resource
from . import auth

logger = logging.getLogger(__name__)

# CSRF token for the page's forms (mirrors the sign-in form's token).
KEYS_CSRF_KEY = "audit_keys_csrf"

# How many keys the page lists. The API's list route is paginated; the
# page shows the most recent keys, and says so when the cap is hit.
KEY_LIST_LIMIT = 200

# The scope vocabulary the page offers, with what each is for. The
# names double as the role catalogue's building blocks (#918).
SCOPE_HELP = (
    ("traces:read", "read traces in the browser and query them via the API"),
    ("traces:search", "search traces via the API"),
    ("traces:write", "ingest spans (a tracing producer's scope)"),
    ("apikeys:read", "list API keys via the API"),
    ("apikeys:write", "create, re-scope, rotate and revoke API keys"),
)


def require_login_keys() -> werkzeug.Response | None:
    """Before-request gate for the key-management page.

    Returns None to allow the request when the session holds the
    key-management capability. A session without it gets the 403 page
    explaining which capability is missing; an unauthenticated browser
    is sent to the login page.
    """
    if not auth.is_authenticated():
        return flask.redirect(flask.url_for("audit_auth.login"))
    if auth.can_manage_keys():
        return None
    return auth.forbidden_page(
        "Your session cannot manage API keys. Managing keys needs the "
        "apikeys:write scope, or a campus.audit superadmin account."
    )


def _csrf_token() -> str:
    """Issue a CSRF token for the page's forms and remember it."""
    token = secrets.token_urlsafe(32)
    flask.session[KEYS_CSRF_KEY] = token
    return token


def _check_csrf() -> bool:
    """Validate the submitted CSRF token (single-use).

    The comparison runs on bytes: compare_digest() raises TypeError on
    non-ASCII strings, and the submitted token is raw form data.
    """
    issued = flask.session.pop(KEYS_CSRF_KEY, None)
    submitted = flask.request.form.get('csrf_token', '')
    if not isinstance(issued, str):
        return False
    return hmac.compare_digest(
        issued.encode('utf-8'), str(submitted).encode('utf-8')
    )


def _actor_tags() -> tuple[str | None, dict[str, typing.Any]]:
    """The acting principal, for attributing a mutation.

    Returns (api_key_id, tags): the key id for an API-key session
    (also the span's api_key_id), or None plus the account in the tags
    for a superadmin session — campus.audit has no user store, and its
    spans carry user_id=None by design.
    """
    actor = auth.current_actor()
    if actor is None:
        return None, {}
    actor_class, actor_id = actor
    if actor_class == auth.ACTOR_API_KEY:
        return actor_id, {"actor_class": actor_class}
    return None, {"actor_class": actor_class, "user_id": actor_id}


def _emit_key_event(
        event_type: str,
        *,
        key_id: str | None = None,
        extra: dict[str, typing.Any] | None = None,
) -> None:
    """Record a key-management action in the audit trail.

    The event types match the versioned API's (audit.apikeys.new,
    .update, .revoke, .regenerate), so one query covers both surfaces.
    """
    from ..helpers.audit_events import emit_web_event

    api_key_id, tags = _actor_tags()
    emit_web_event(
        event_type=event_type,
        data={"surface": "audit-web-keys", **tags, **(extra or {})},
        api_key_id=api_key_id,
        status_code=200,
    )


def _key_rows() -> list[dict[str, typing.Any]]:
    """The keys the page lists, newest first."""
    records = apikeys_resource.list_keys(
        owner_id=None, active_only=False, limit=KEY_LIST_LIMIT
    )
    rows = []
    for record in records:
        resource = record.to_resource()
        rows.append({
            "id": str(resource.get("id", "")),
            "name": str(resource.get("name", "")),
            "owner_id": str(resource.get("owner_id", "")),
            "scopes": list(resource.get("scopes") or []),
            "created_at": str(resource.get("created_at", "")),
            "expires_at": str(resource.get("expires_at") or ""),
            "revoked_at": str(resource.get("revoked_at") or ""),
            "last_used": str(resource.get("last_used") or ""),
            "rate_limit": resource.get("rate_limit"),
            "revoked": bool(resource.get("revoked_at")),
        })
    return rows


def _render_page(
        *,
        status: int = 200,
        minted: str | None = None,
        notice: str | None = None,
        error: str | None = None,
) -> flask.Response:
    """Render the key-management page.

    A response carrying a plaintext (minted or rotated) is marked
    no-store, so it does not linger in a browser cache or a proxy.
    """
    html = flask.render_template(
        'keys.html',
        keys=_key_rows(),
        csrf_token=_csrf_token(),
        minted=minted,
        notice=notice,
        error=error,
        scope_help=SCOPE_HELP,
        key_limit=KEY_LIST_LIMIT,
    )
    response = flask.make_response(html, status)
    response.headers['Cache-Control'] = 'no-store'
    return response


def _form_error(message: str) -> flask.Response:
    """Re-render the page with an error and a fresh CSRF token."""
    return _render_page(status=400, error=message)


def _parse_scopes(raw: str) -> list[str]:
    """Parse a comma-separated scope list."""
    return [scope.strip() for scope in raw.split(',') if scope.strip()]


def _parse_expires_at(raw: str) -> schema.DateTime | None:
    """Validate an ISO 8601 expiry, returning None for "no expiry".

    The value is checked here because the key's own expiry check parses
    it later — a malformed date would break the key's authentication
    rather than the form.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(
            "The expiry must be an ISO 8601 date-time (e.g. "
            "2026-12-31T23:59:59+00:00)."
        ) from None
    return schema.DateTime(raw)


def create_blueprint() -> flask.Blueprint:
    """Create the blueprint for the key-management page.

    Returns:
        A Flask blueprint serving the key-management page
    """
    bp = flask.Blueprint(
        'audit_keys',
        __name__,
        url_prefix='/audit/keys',
    )
    bp.before_request(require_login_keys)

    @bp.get('')
    def index() -> flask.Response:
        """The key-management page: the key list and the mint form."""
        return _render_page()

    @bp.post('/new')
    def new() -> flask.Response:
        """Mint a key. The plaintext is shown once, here, and nowhere
        else — it is never stored."""
        if not _check_csrf():
            return _form_error(
                "Your form session expired. Please reload the page and "
                "try again."
            )
        name = (flask.request.form.get('name') or '').strip()
        owner_id = (flask.request.form.get('owner_id') or '').strip()
        scopes = _parse_scopes(flask.request.form.get('scopes') or '')
        if not name:
            return _form_error("Give the key a name.")
        if not owner_id:
            return _form_error(
                "Give the key an owner — the email of the person it is "
                "for. It is a display label only, never resolved."
            )
        if not scopes:
            return _form_error("Give the key at least one scope.")
        rate_limit_raw = (flask.request.form.get('rate_limit') or '').strip()
        rate_limit: int | None = None
        if rate_limit_raw:
            try:
                rate_limit = int(rate_limit_raw)
            except ValueError:
                return _form_error(
                    "The rate limit must be a whole number of requests "
                    "per minute."
                )
        try:
            expires_at = _parse_expires_at(
                flask.request.form.get('expires_at') or ''
            )
        except ValueError as e:
            return _form_error(str(e))
        record, plaintext = apikeys_resource.new(
            name=name,
            owner_id=owner_id,
            scopes=",".join(scopes),
            rate_limit=rate_limit,
            expires_at=expires_at,
        )
        logger.info(
            "Audit UI minted key %s (owner %s)", record.id, owner_id,
        )
        _emit_key_event(
            "audit.apikeys.new",
            key_id=record.id,
            extra={"owner_id": owner_id, "scopes": scopes},
        )
        return _render_page(
            minted=plaintext,
            notice=(
                f"Key '{name}' created. Copy the key below now — it is "
                "shown only here, and the server keeps only its hash."
            ),
        )

    @bp.post('/<key_id>/scopes')
    def update_scopes(key_id: str) -> flask.Response:
        """Change a key's scopes."""
        if not _check_csrf():
            return _form_error(
                "Your form session expired. Please reload the page and "
                "try again."
            )
        scopes = _parse_scopes(flask.request.form.get('scopes') or '')
        if not scopes:
            return _form_error("Give the key at least one scope.")
        try:
            apikeys_resource[key_id].update(scopes=scopes)
        except api_errors.NotFoundError:
            return _form_error(f"No key with id {key_id}.")
        except api_errors.ForbiddenError as e:
            return _form_error(str(e))
        except api_errors.InvalidRequestError as e:
            return _form_error(str(e))
        logger.info("Audit UI re-scoped key %s", key_id)
        _emit_key_event(
            "audit.apikeys.update",
            key_id=key_id,
            extra={"scopes": scopes},
        )
        return _render_page(
            notice=f"Scopes updated for key {key_id}."
        )

    @bp.post('/<key_id>/rotate')
    def rotate(key_id: str) -> flask.Response:
        """Rotate a key: a new plaintext, the same key id. The old key
        stops working immediately."""
        if not _check_csrf():
            return _form_error(
                "Your form session expired. Please reload the page and "
                "try again."
            )
        try:
            plaintext = apikeys_resource[key_id].regenerate()
        except api_errors.NotFoundError:
            return _form_error(f"No key with id {key_id}.")
        logger.info("Audit UI rotated key %s", key_id)
        _emit_key_event("audit.apikeys.regenerate", key_id=key_id)
        return _render_page(
            minted=plaintext,
            notice=(
                f"Key {key_id} rotated. The previous key no longer works. "
                "Copy the new key now — it is shown only here."
            ),
        )

    @bp.post('/<key_id>/revoke')
    def revoke(key_id: str) -> flask.Response:
        """Revoke a key. Revoking is the only way to withdraw access
        a holder was given."""
        if not _check_csrf():
            return _form_error(
                "Your form session expired. Please reload the page and "
                "try again."
            )
        if not apikeys_resource[key_id].revoke():
            return _form_error(f"No key with id {key_id}.")
        logger.info("Audit UI revoked key %s", key_id)
        _emit_key_event("audit.apikeys.revoke", key_id=key_id)
        return _render_page(
            notice=(
                f"Key {key_id} revoked. It no longer authenticates "
                "anything, for anyone."
            ),
        )

    return bp
