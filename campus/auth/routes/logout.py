"""campus.auth.routes.logout

Browser-session logout route for the auth service.

Identity login stores the signed-in user in this service's Flask
session and issues its session cookie to the browser. App-side
sign-out only revokes the login_sessions record through the API
(#776); this endpoint is the browser-session half (#785): it clears
the SSO session so the browser stops presenting a live campusauth
cookie.
"""

import logging
from urllib.parse import urlparse

import flask
import werkzeug

from .. import resources

logger = logging.getLogger(__name__)

# Create blueprint for the browser-session logout route.
# No url_prefix: the route lives at the top level of /auth/v1.
bp = flask.Blueprint('logout', __name__)


def _registered_client_origins() -> set[tuple[str, str]]:
    """Origins (scheme, netloc) of all registered client redirect_uris.

    The post-logout allowlist source (#788): first-party apps already
    register their OAuth callback redirect_uris — login validation is
    fail-closed on them (#651, RFC 6749 §3.1.2.2) — so the service
    knows their origins without new configuration. A deployment with
    no registered redirect_uris degrades gracefully: every absolute
    target is rejected and logout lands on "/".

    Per-client matching (client_id/id_token_hint) is #301's job; any
    app's logout may currently land on any registered app's origin.
    All registered clients are first-party, so this is accepted.
    """
    origins: set[tuple[str, str]] = set()
    for client in resources.client.list_all():
        for redirect_uri in client.redirect_uris or []:
            parsed = urlparse(redirect_uri)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                origins.add(
                    (parsed.scheme.lower(), parsed.netloc.lower())
                )
    return origins


def _is_safe_redirect(
        target: str,
        registered_origins: set[tuple[str, str]],
) -> bool:
    """Ensure URL is safe for redirect (prevents open redirect attacks).

    Same-origin relative URLs only (the discipline of flask_campus's
    login `next` check), hardened against the backslash spelling of a
    protocol-relative URL (`/\\evil.example.com` normalizes to
    `//evil.example.com` in browsers) — plus absolute URLs whose
    origin is registered by an OAuth client (#788). Anything else,
    including authorities carrying userinfo or backslashes, fails
    closed.
    """
    if target.startswith('/') and not target.startswith(('//', '/\\')):
        return True
    parsed = urlparse(target)
    if (
            parsed.scheme in ("http", "https")
            and parsed.netloc
            and "@" not in parsed.netloc
            and "\\" not in parsed.netloc
    ):
        return (
            parsed.scheme.lower(),
            parsed.netloc.lower()
        ) in registered_origins
    return False


@bp.get("/logout")
def logout() -> werkzeug.Response:
    """Clear the campusauth browser session and redirect.

    GET /logout?post_logout_redirect_uri=/some/path

    Clears the auth service's Flask session (dropping user_id and the
    login session binding) and expires its cookie, then redirects the
    browser to the validated target.

    Query parameters:
        - post_logout_redirect_uri: same-origin path, or an absolute
          URL whose origin matches a registered client's redirect_uri
          (#788), so sign-out can land the browser back on the calling
          app. The OIDC parameter name is deliberate so #301's optional
          RP-initiated logout (end_session_endpoint) can adopt or
          absorb this endpoint. Absent or unsafe targets fall back to
          "/". Google's browser session is deliberately unaffected:
          signing out of Google itself is a per-app product choice,
          not a framework default (#785, out of scope).

    Responses:
        302 Found: Redirect to the validated target.
    """
    flask.session.clear()
    try:
        registered_origins = _registered_client_origins()
    except Exception:
        # Fail closed: an allowlist lookup failure must not block the
        # sign-out itself, only the redirect-back-to-app convenience.
        logger.exception(
            "Failed to list registered client redirect_uris; "
            "post_logout_redirect_uri will only accept same-origin paths"
        )
        registered_origins = set()
    target = flask.request.args.get("post_logout_redirect_uri") or "/"
    if not _is_safe_redirect(target, registered_origins):
        target = "/"
    return flask.redirect(target)


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('logout', __name__)
    new_bp.add_url_rule("/logout", "logout", logout, methods=["GET"])
    return new_bp
