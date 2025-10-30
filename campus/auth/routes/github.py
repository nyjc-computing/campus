"""campus.auth.routes.github

Proxy and callback routes for GitHub OAuth2 authentication.
"""

from typing import Literal

import flask
import werkzeug

from campus.client.vault import get_vault
import campus.integrations as integrations
from campus.common import schema
from campus.common.errors import auth_errors, token_errors
from campus.common.validation import flask as flask_validation
from campus.models import session, token, webauth

PROVIDER = 'github'

tokens = token.Tokens()

auth_sessions = session.AuthSessions(PROVIDER)
vault = get_vault()[PROVIDER]
bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauth2 = webauth.oauth2.OAuth2FlowScheme.from_config(
    provider=PROVIDER,
    config=integrations.get_config(PROVIDER),
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/authorize')
@flask_validation.unpack_request
def authorize(
        target: schema.Url,
        prompt: Literal["select_account"] | None = None
) -> werkzeug.Response:
    """Redirect to GitHub OAuth authorization endpoint."""
    redirect_uri = flask.url_for('.callback', _external=True)
    oauth2.init_session(
        redirect_uri=redirect_uri,
        client_id=vault["CLIENT_ID"].get()['value'],
        scopes=oauth2.scopes,
        target=target
    )
    authorization_url = oauth2.get_authorization_url(
        **{"prompt": prompt} if prompt else {}
    )
    return flask.redirect(authorization_url)


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """Handle a GitHub OAuth callback request."""
    callback_payload = flask_validation.get_request_payload()
    if "error" in callback_payload:
        auth_errors.raise_from_json(callback_payload)
    else:
        return flask_validation.unpack_into(success_callback,
                                            **callback_payload)


def success_callback(
        state: str,
        code: str,  # on success
        scope: str,  # on success
        prompt: str | None = None  # on success
) -> werkzeug.Response:
    """Handle a Github OAuth callback request."""
    oauth2.validate_callback(state)
    client_id = vault["CLIENT_ID"].get()["value"]
    client_secret = vault["CLIENT_SECRET"].get()["value"]
    # Retrieve access token from GitHub
    token = oauth2.exchange_code_for_token(
        code=code,
        client_id=client_id,
        client_secret=client_secret,
    )
    # Verify requested scopes were granted
    scopes = scope.split(" ")
    if missing_scopes := token.validate_scope(scopes):
        raise auth_errors.InvalidScopeError(
            f"Missing scopes: {', '.join(missing_scopes)}"
        )
    # Store token
    tokens.store(token)
    target = oauth2.auth_session.target
    oauth2.end_session()
    return flask.redirect(target or flask.request.host_url)
