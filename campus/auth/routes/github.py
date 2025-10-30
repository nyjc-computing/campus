"""campus.auth.routes.github

Proxy and callback routes for GitHub OAuth2 authentication.
"""

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
def authorize(target: schema.Url) -> werkzeug.Response:
    """Redirect to GitHub OAuth authorization endpoint."""
    redirect_uri = flask.url_for('.callback', _external=True)
    auth_session = oauth2.init_session(
        redirect_uri=redirect_uri,
        client_id=vault["CLIENT_ID"].get()['value'],
        scopes=oauth2.scopes,
        target=target
    )
    authorization_url = oauth2.get_authorization_url()
    return flask.redirect(authorization_url)


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """Handle a GitHub OAuth callback request."""
    callback_payload = flask_validation.get_request_payload()
    if "error" in callback_payload:
        return flask_validation.unpack_into(error_callback,
                                            **callback_payload)
    else:
        return flask_validation.unpack_into(success_callback,
                                            **callback_payload)


def error_callback(
        error: str,
        error_description: str,
        error_uri: str
) -> werkzeug.Response:
    """Handle a Github OAuth error callback request."""
    auth_errors.raise_from_error(error, error_description)  # type: ignore


def success_callback(
        state: str,
        code: str,  # on success
        scope: str,  # on success
        authuser: str,  # on success
        hd: str,  # on success
        prompt: str  # on success
) -> werkzeug.Response:
    """Handle a Github OAuth callback request."""
    auth_session = oauth2.retrieve_session()
    error_description = None
    if not auth_session:
        error_description = "No active OAuth session found."
    elif auth_session.is_expired():
        error_description = "OAuth session has expired."
    elif auth_session.id != state:
        error_description = "Session state mismatch."
    elif auth_session.redirect_uri is None:
        error_description = "No redirect URI in auth session."
    if error_description:
        raise auth_errors.InvalidRequestError(error_description)
    assert auth_session.redirect_uri
    client_secret = vault["CLIENT_SECRET"].get()["value"]

    # Retrieve access token from GitHub
    token = oauth2.exchange_code_for_token(
        code=code,
        client_secret=client_secret,
        redirect_uri=auth_session.redirect_uri
    )
    # user_id is needed to store creds
    user_info = oauth2.get_user_info(token.access_token)
    if "error" in user_info:
        raise token_errors.raise_from_error(
            error=user_info["error"],
            error_description=user_info.get("error_description", ""),
            error_uri=user_info.get("error_uri")
        )

    token = tokens.new(
        client_id=vault["CLIENT_ID"].get()["value"],
        user_id=user_info["id"],
        scopes=token.scopes,
        expiry_seconds=token.expires_in
    )
    assert token.access_token  # for static checkers

    # Verify requested scopes were granted
    if missing_scopes := token.validate_scope(auth_session.scopes):
        raise auth_errors.InvalidScopeError(
            f"Missing required scopes: {', '.join(missing_scopes)}"
        )

    auth_sessions.delete()
    return flask.redirect(oauth2.auth_session.target
                          or flask.request.host_url)
