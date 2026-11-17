"""campus.auth.oauth_proxy.errors

Shared rendering for upstream OAuth error redirects.

The proxy callbacks receive upstream error redirects as query data
(RFC 6749 §4.1.2.1: `error`, `error_description`, `error_uri`, plus
`state`). This module renders them as one clean, escaped error page for
all providers — the payload is client-forgeable, so echoing it raw was
both an information leak and a reflected-XSS surface (#1127).
"""

__all__ = [
    "oauth_error_response",
]

import logging
from html import escape

import flask
import werkzeug

logger = logging.getLogger(__name__)


def oauth_error_response(callback_payload: dict) -> werkzeug.Response:
    """Render an upstream OAuth error redirect as a clean error page.

    Nothing from the payload is echoed except the fixed error code, and
    that value is HTML-escaped. The full payload goes to the server log
    instead — Railway logs are the superadmin debug surface
    (environment-access-policy §3), while the browser page is a student
    surface and must be clear without leaking internals (policy §4).
    """
    error_code = escape(str(callback_payload.get("error", "unknown_error")))
    path = flask.request.path if flask.has_request_context() else "oauth-callback"
    logger.warning("OAuth callback error on %s: %r", path, callback_payload)
    page = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Sign-in error</title></head>
    <body>
        <h1>Sign-in error</h1>
        <p>Sign-in could not be completed (error code:
        <code>{error_code}</code>).</p>
        <p>Please go back and try signing in again. If the problem
        persists, contact the ICT department.</p>
    </body>
    </html>
    """
    return flask.Response(page, status=400, mimetype="text/html")
