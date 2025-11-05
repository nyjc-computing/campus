"""campus.auth.oauth_proxy.discord.proxy

Discord OAuth2 proxy implementation.
"""

__all__ = ["DiscordAuthPoxy", "get_proxy"]

from typing import Literal

import flask
import werkzeug

from campus.common import env, schema
from campus.common.errors import auth_errors
import campus.config
from campus.models import webauth

from .. import base
from ... import resources

PROVIDER = "discord"
REDIRECT_URI = schema.Url(env.HOSTNAME + f"/auth/{PROVIDER}/callback")
SCOPE_SEP = " "


def get_proxy() -> "DiscordAuthPoxy":
    """Get an instance of the DiscordAuthPoxy."""
    return DiscordAuthPoxy()


class DiscordAuthPoxy(base.AuthProxy):
    """Discord OAuth2 provider implementation."""
    provider = PROVIDER
    title = "Discord OAuth2 Authentication API"
    description = "OAuth2 authentication endpoints for Discord integration with Campus"
    version = "10.0.0"
    openapi_version = "3.0.3"
    authorization_url = schema.Url(
        "https://discord.com/oauth2/authorize"
    )
    token_url = schema.Url("https://discord.com/api/oauth2/token")
    user_info_url = schema.Url(
        "https://discord.com/api/users/@me"
    )
    _headers = {"Accept": "application/json"}
    _oauth2: webauth.oauth2.OAuth2AuthorizationCodeFlowScheme
    _PROMPT_OPTIONS = Literal["consent", "none"] | None

    def __init__(self) -> None:
        super().__init__()
        self._oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
            provider=PROVIDER,
            authorization_url=self.authorization_url,
            token_url=self.token_url,
            user_info_url=self.user_info_url,
            scopes=["identify", "email", "guilds"],
            headers=self._headers,
        )

    def redirect_for_authorization(
            self,
            target: schema.Url,
            *,
            prompt: _PROMPT_OPTIONS = None,  # common option for providers
    ) -> werkzeug.Response:
        """Redirect to GitHub OAuth2 authorization endpoint."""
        authsession = resources.session[PROVIDER].new(
            expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
            client_id=self._CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            scopes=self._oauth2.scopes,
            target=target
        )
        # self._oauth2.init_session(
        #     redirect_uri=REDIRECT_URI,
        #     client_id=self._CLIENT_ID,
        #     scopes=self._oauth2.scopes,
        #     target=target
        # )
        url_params = {}
        if prompt:
            url_params["prompt"] = prompt
        authorization_url = self._oauth2.get_authorization_url(**url_params)
        return flask.redirect(authorization_url)

    def handle_callback(
            self,
            state: str,
            code: str,
            scope: str,
            **kwargs: str
    ) -> werkzeug.Response:
        assert self._oauth2 is not None
        self._oauth2.validate_callback(state=state)
        # Retrieve access token from GitHub
        # Fill in user info from userinfo endpoint
        token = self._oauth2.exchange_code_for_token(
            code=code,
            client_id=self._CLIENT_ID,
            client_secret=self._CLIENT_SECRET,
        )
        # Verify requested scopes were granted
        scopes = scope.split(SCOPE_SEP)
        if missing_scopes := token.validate_scope(scopes):
            raise auth_errors.InvalidScopeError(
                f"Missing required scopes: {', '.join(missing_scopes)}"
            )
        userinfo = self._oauth2.get_user_info(token.access_token)
        user_id = schema.Email(userinfo["email"])
        # Store/update token
        resources.credentials[PROVIDER][user_id].update(
            client_id=self._CLIENT_ID,
            token=token,
        )
        target = self._oauth2.auth_session.target
        self._oauth2.end_session()
        return flask.redirect(target or flask.request.host_url)
