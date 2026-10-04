"""campus.auth.routes.logout

Browser-session logout route for the auth service.

Identity login stores the signed-in user in this service's Flask
session and issues its session cookie to the browser. App-side
sign-out only revokes the login_sessions record through the API
(#776); this endpoint is the browser-session half (#785): it clears
the SSO session so the browser stops presenting a live campusauth
cookie.
"""

import flask
import werkzeug

# Create blueprint for the browser-session logout route.
# No url_prefix: the route lives at the top level of /auth/v1.
bp = flask.Blueprint('logout', __name__)


def _is_safe_redirect(target: str) -> bool:
    """Ensure URL is safe for redirect (prevents open redirect attacks).

    Same relative-URL-only discipline as flask_campus.login_manager's
    login `next` check (#785), hardened against the backslash spelling
    of a protocol-relative URL (`/\\evil.example.com` normalizes to
    `//evil.example.com` in browsers). #301's RP-initiated logout can
    widen this to registered post-logout URIs when it absorbs this
    endpoint.
    """
    return (
        target.startswith('/')
        and not target.startswith('//')
        and not target.startswith('/\\')
    )


@bp.get("/logout")
def logout() -> werkzeug.Response:
    """Clear the campusauth browser session and redirect.

    GET /logout?post_logout_redirect_uri=/some/path

    Clears the auth service's Flask session (dropping user_id and the
    login session binding) and expires its cookie, then redirects the
    browser to the validated target.

    Query parameters:
        - post_logout_redirect_uri: optional same-origin path to land
          on after sign-out. The OIDC parameter name is deliberate so
          #301's optional RP-initiated logout (end_session_endpoint)
          can adopt or absorb this endpoint. Absent, cross-origin or
          otherwise unsafe targets fall back to "/". Google's browser
          session is deliberately unaffected: signing out of Google
          itself is a per-app product choice, not a framework default
          (#785, out of scope).

    Responses:
        302 Found: Redirect to the validated target.
    """
    flask.session.clear()
    target = flask.request.args.get("post_logout_redirect_uri") or "/"
    if not _is_safe_redirect(target):
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
