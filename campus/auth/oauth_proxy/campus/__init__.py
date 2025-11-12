"""campus.auth.routes.campus

Routes for Campus OAuth2.

While Campus supports the full OAuth2 flow (e.g. for third-party
clients), first-party clients may use this module so they don't have to
implement server-side storage for session management.
"""

import flask
import werkzeug

from campus.common import flask as campus_flask, schema
from campus.common.errors import auth_errors

from . import proxy

PROVIDER = 'campus'

bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.before_request
def before_request() -> None:
    flask.g.proxy = proxy.get_proxy()


@bp.get('/authorize')
@campus_flask.unpack_request
def authorize(
        target: schema.Url,
        login_hint: schema.Email | None = None,
) -> werkzeug.Response:
    """Prepares the Campus OAuth authorization URL and redirects to it.
    """
    return flask.g.proxy.redirect_for_authorization(
        target,
        login_hint=login_hint,
    )


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """Handles the Campus OAuth callback request.

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
    """Campus uses Google SSO for authentication. This function handles
    the Google OAuth callback request for an auth flow.
    """
    return flask.g.proxy.handle_callback(
        state,
        code,
        scope,
        **kwargs
    )
