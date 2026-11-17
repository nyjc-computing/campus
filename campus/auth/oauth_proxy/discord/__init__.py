"""campus.auth.oauth_proxy.discord

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

import campus.flask_campus as flask_campus
from campus.common import schema

from ..errors import oauth_error_response
from . import proxy

PROVIDER = "discord"


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise Discord OAuth routes with the given Flask app/blueprint.

    Creates a fresh blueprint each time to support test isolation.
    """
    bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f"/{PROVIDER}")

    @bp.before_request
    def before_request() -> None:
        flask.g.proxy = proxy.get_proxy()

    @bp.get("/authorize")
    @flask_campus.unpack_request
    def authorize(
            target: schema.Url,
            prompt: Literal["consent", "none"] | None = None
    ) -> werkzeug.Response:
        """Start the Discord login flow
"""
        return flask.g.proxy.redirect_for_authorization(
            target,
            prompt=prompt
        )

    @bp.get("/callback")
    def callback() -> werkzeug.Response:
        """Discord redirect target

        Dispatches to success or error handlers based on payload type.
        """
        callback_payload = flask_campus.get_request_payload()
        if "error" in callback_payload:
            return oauth_error_response(callback_payload)
        else:
            return flask_campus.unpack_into(success_callback,
                                            **callback_payload)

    def success_callback(
            state: str,
            code: str,
            scope: str,
            **kwargs: str
    ) -> werkzeug.Response:
        """Handle a Discord OAuth callback request."""
        return flask.g.proxy.handle_callback(
            state,
            code,
            scope,
            **kwargs
        )

    app.register_blueprint(bp)
