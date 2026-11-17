"""campus.auth.oauth_proxy.github

Proxy and callback routes for GitHub OAuth2 authentication.
"""

from typing import Literal

import flask
import werkzeug

import campus.flask_campus as flask_campus
from campus.common import schema

from ..errors import oauth_error_response
from . import proxy

PROVIDER = 'github'


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
            prompt: Literal["select_account"] | None = None
    ) -> werkzeug.Response:
        """Start the GitHub login flow
"""
        return flask.g.proxy.redirect_for_authorization(target, prompt)

    @bp.get('/callback')
    def callback() -> werkzeug.Response:
        """GitHub redirect target
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
        """Handle a Github OAuth callback request."""
        return flask.g.proxy.handle_callback(
            state,
            code,
            scope,
            **kwargs
        )

    app.register_blueprint(bp)
