"""campus.auth.routes.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server

Google OAuth 2.0 Authorization Flow Diagram:

+--------+        (A)        +---------+
|        |------------------>| Google  |
|        |   Auth Request    |         |
|        |                   +---------+
|        |        (B)        +---------+
|        | +-----------------|         |
|  User  | +---------------->|         |     (C)       +-----------+
|        | Redirect w/ Code  | Campus  |---------------|  Google   |
|        |                   | Backend |<--------------|  Token    |
|        |        (D)        |         | Token Request | Endpoint  |
|        |<----------------- |         |               +-----------+
+--------+ Redirect to sess  +---------+
                target

Legend:
(A) User is redirected from Campus to Google for authentication and consent.
    - a server-side session is initialised
    - the session_id is stored client-side
(B) Google redirects the user back to Campus with an authorization code.
(C) Campus backend exchanges the authorization code directly with Google's
    token endpoint for user profile.
(D) Campus redirects user to session target.

Apps and view functions sending the user to this endpoint must first establish
a server-side session with a target.
"""

import logging
from typing import Literal
from urllib.parse import urlparse

import flask
import werkzeug

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from ... import integrations
from ... import scopes as campus_scopes
from . import proxy
from .proxy import get_proxy as get_proxy  # noqa: F401 (re-export)

logger = logging.getLogger(__name__)

PROMPT_OPTION = Literal["consent", "login", "none", "select_account"]
PROVIDER = 'google'
# The Workspace domain pinned on authorization requests (identity and
# connect alike); the callback re-checks it against the userinfo email.
HD_DEFAULT = "nyjc.edu.sg"


def _oauth_error_response(callback_payload: dict) -> werkzeug.Response:
    """Render an OAuth error payload as an error page.

    TODO: For testing - display error instead of redirecting
    This should be replaced with proper error handling that redirects to target
    """
    error_html = f"""
    <html>
    <head><title>OAuth Error</title></head>
    <body>
        <h1>OAuth Error</h1>
        <p><strong>Error:</strong> {callback_payload.get('error')}</p>
        <p><strong>Description:</strong> {callback_payload.get('error_description', 'N/A')}</p>
        <p><strong>Error URI:</strong> {callback_payload.get('error_uri', 'N/A')}</p>
        <hr>
        <p><strong>All callback parameters:</strong></p>
        <pre>{callback_payload}</pre>
    </body>
    </html>
    """
    return flask.Response(error_html, status=400, mimetype='text/html')


def _require_campus_session() -> str:
    """Return the signed-in campus user or deny the connect flow.

    The connect flow stores an upstream credential for the browser's
    campus session user, so it must never run without one (design §2.3
    guard 1). The identity authorize route stays open: login needs it
    pre-auth.
    """
    user_id = flask.session.get('user_id')
    if not user_id:
        raise api_errors.UnauthorizedError(
            "Campus session required; sign in before connecting an "
            "integration"
        )
    return user_id


def _validate_connect_target(
        target: schema.Url,
        connect_targets: tuple[str, ...],
) -> None:
    """Fail closed on connect targets outside the vault allowlist.

    A flow that stores upstream tokens must not double as an open
    redirector: the target's origin must be an HTTPS origin registered
    in the integration's vault CONNECT_TARGETS (design §2.3 guard 2).
    """
    parsed = urlparse(str(target))
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.scheme != "https" or origin not in connect_targets:
        raise api_errors.InvalidRequestError(
            "Connect target origin is not registered for this "
            "integration",
            target_origin=origin,
        )


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint.

    Creates a fresh blueprint each time to support test isolation.
    """
    bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')

    @bp.before_request
    def before_request() -> None:
        flask.g.proxy = proxy.get_proxy()

    @bp.get('/authorize')
    @flask_campus.unpack_request
    def authorize(
            target: schema.Url,
            hd: str | None = HD_DEFAULT,
            login_hint: schema.Email | None = None,
            prompt: PROMPT_OPTION | None = None,
            scope: str | None = None,
    ) -> werkzeug.Response:
        """Prepares the Google OAuth authorization URL and redirects to it.

        scope (space-delimited) requests upstream Google scopes beyond
        the proxy's base set (email, profile), merged via
        include_granted_scopes=true so re-consent accumulates
        (invariant B3, docs/auth-token-invariants.md). The app path
        reaches this endpoint through provider.authorize, which caps
        the requested scopes against the campus client's
        upstream_scopes allowlist before forwarding them here; what the
        broker may later release is re-checked against the same
        allowlist.
        """
        return flask.g.proxy.redirect_for_authorization(
            target,
            hd=hd,
            login_hint=login_hint,
            prompt=prompt,
            extra_scopes=campus_scopes.parse(scope),
        )

    @bp.get('/callback')
    def callback() -> werkzeug.Response:
        """Handles the Google OAuth callback request.

        Dispatches to success or error handlers based on payload type.
        """
        callback_payload = flask_campus.get_request_payload()
        if "error" in callback_payload:
            return _oauth_error_response(callback_payload)
        else:
            return flask_campus.unpack_into(success_callback,
                                            **callback_payload)

    @bp.get('/<integration>/authorize')
    @flask_campus.unpack_request
    def integration_authorize(
            integration: str,
            target: schema.Url,
    ) -> werkzeug.Response:
        """Start the connect consent flow for an integration (#733).

        Guards (design §2.3), all enforced here, not just in the
        calling app:
        1. the browser must hold a campus session (the user logs in via
           the identity flow first);
        2. the integration must be a registry entry with a configured
           vault client, and connect must be enabled (non-empty
           CONNECT_TARGETS);
        3. the target must be an HTTPS origin in CONNECT_TARGETS.

        Consent is forced (prompt=consent) so the stored credential
        always carries a refresh token, the asked scopes are exactly
        the vault SCOPES cap, and the redirect lands on the
        integration's own callback path (each integration's Google
        client registers its own callback URL in Google Cloud). Connect
        is a user-session flow: no campus client allowlist applies
        here; per-app policy is enforced at the broker.
        """
        _require_campus_session()
        campus_integration = integrations.get(integration)
        connect_proxy = proxy.get_proxy(campus_integration)
        if not connect_proxy.connect_targets:
            raise api_errors.NotFoundError(
                f"Integration {campus_integration.provider!r} is not "
                "open for connections",
                integration=campus_integration.slug,
            )
        _validate_connect_target(target, connect_proxy.connect_targets)
        return connect_proxy.redirect_for_authorization(
            target,
            hd=HD_DEFAULT,
            prompt="consent",
        )

    @bp.get('/<integration>/callback')
    def integration_callback(integration: str) -> werkzeug.Response:
        """Handles the Google OAuth callback for a connect flow.

        Dispatches to the integration proxy's consent handler, which
        binds the credential to the campus session user (403 on
        mismatch) instead of setting the session, and stores it under
        the integration's namespaced provider.
        """
        campus_integration = integrations.get(integration)
        connect_proxy = proxy.get_proxy(campus_integration)
        callback_payload = flask_campus.get_request_payload()
        if "error" in callback_payload:
            return _oauth_error_response(callback_payload)
        return flask_campus.unpack_into(
            connect_proxy.handle_consent_callback,
            **callback_payload
        )

    def success_callback(
            state: str,
            code: str,
            scope: str,
            **kwargs: str
    ) -> werkzeug.Response:
        """Handle a Google OAuth callback request."""
        return flask.g.proxy.handle_consent_callback(
            state,
            code,
            scope,
            **kwargs
        )

    app.register_blueprint(bp)
