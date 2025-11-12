"""campus.auth.routes.github

Proxy and callback routes for GitHub OAuth2 authentication.
"""

from typing import Literal

import flask
import werkzeug

from campus.common import flask_campus, schema
from campus.common.errors import auth_errors

from . import proxy

PROVIDER = 'github'

bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


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
        auth_errors.raise_from_json(callback_payload)
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
