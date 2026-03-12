"""campus.auth.routes.github

Proxy and callback routes for GitHub OAuth2 authentication.
"""

from typing import Literal

import flask
import werkzeug

from campus import flask_campus
from campus.common import schema
from campus.common.errors import auth_errors

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
        """Redirect to GitHub OAuth authorization endpoint."""
        return flask.g.proxy.redirect_for_authorization(target, prompt)

    @bp.get('/callback')
    def callback() -> werkzeug.Response:
        """Handle a GitHub OAuth callback request."""
        callback_payload = flask_campus.get_request_payload()
        if "error" in callback_payload:
            # TODO: For testing - display error instead of redirecting
            # This should be replaced with proper error handling that redirects to target
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
