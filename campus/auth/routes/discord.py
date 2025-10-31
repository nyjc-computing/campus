"""campus.auth.routes.discord

Routes for Discord OAuth2 Client Credentials flow.

Reference: https://discord.com/developers/docs/topics/oauth2

Discord OAuth 2.0 Client Credentials Flow:

+--------+        (A)        +---------+ 
|        |------------------>| Discord |
| Campus |   Token Request    |         | 
| Server |   (Basic Auth)    +---------+ 
|        |        (B)        +---------+
|        |<------------------|         |
|        |   Access Token    | Campus  |
|        |                   | Backend |
+--------+                   +---------+

Legend:
(A) Campus server requests an app token using client credentials
    - Uses Basic Auth with client_id:client_secret
    - Requests application-level scopes only
(B) Discord returns an access token for the application
    - Token can be used for Discord API calls
    - No user context, application-level access only

This flow is suitable for server-to-server authentication where no user
interaction is required.
"""

from typing import Literal

import flask
import werkzeug

from campus.client.vault import get_vault
import campus.integrations as integrations
from campus.common import flask as campus_flask, schema
from campus.common.errors import auth_errors
from campus.models import session, token

PROVIDER = "discord"

tokens = token.Tokens()

auth_sessions = session.AuthSessions(PROVIDER)
vault = get_vault()[PROVIDER]
bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f"/{PROVIDER}")


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise Discord OAuth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.before_request
def before_request() -> None:
    flask.g.provider = integrations.discord.get_provider()


@bp.get("/authorize")
def authorize(
        target: schema.Url,
        prompt: Literal["consent", "none"] | None = None
) -> werkzeug.Response:
    """Prepares the Discord OAuth authorization URL and redirects to it."""
    return flask.g.provider.redirect_for_authorization(
        target,
        prompt=prompt
    )


@bp.get("/callback")
def callback() -> werkzeug.Response:
    """Handles the Discord OAuth callback request.

    Dispatches to success or error handlers based on payload type.
    """
    callback_payload = campus_flask.get_request_payload()
    if "error" in callback_payload:
        auth_errors.raise_from_json(callback_payload)
    else:
        return campus_flask.unpack_into(success_callback,
                                            **callback_payload)


def success_callback(
        state: str,
        code: str,
        scope: str,
        **kwargs: str
) -> werkzeug.Response:
    """Handle a Discord OAuth callback request."""
    return flask.g.provider.handle_callback(
        state,
        code,
        scope,
        **kwargs
    )
