"""campus.auth.oauth_proxy.discord.proxy

Discord OAuth2 proxy implementation.
"""

__all__ = ["DiscordAuthPoxy", "get_proxy"]

from typing import Literal

import flask
import werkzeug

from campus.common import schema, webauth
from campus.common.errors import auth_errors
import campus.config

from .. import base
from ... import resources

PROVIDER = "discord"
SCOPE_SEP = " "


def _get_redirect_uri() -> schema.Url:
    """Get redirect URI with runtime env access."""
    from campus.common import env
    return schema.Url(env.HOSTNAME + f"/auth/{PROVIDER}/callback")


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
    _headers = {"Accept": "application/json"}
    _PROMPT_OPTIONS = Literal["consent", "none"] | None

    def __init__(self) -> None:
        super().__init__()
        # Import env at runtime and create OAuth2 scheme
        from campus.common import env
        self._oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
            provider=PROVIDER,
            client_id=env.CLIENT_ID,
            redirect_uri=_get_redirect_uri(),
            authorization_url=schema.Url(
                "https://discord.com/oauth2/authorize"
            ),
            token_url=schema.Url("https://discord.com/api/oauth2/token"),
            user_info_url=schema.Url(
                "https://discord.com/api/users/@me"
            ),
            scopes=["identify", "email", "guilds"],
            headers={"Accept": "application/json"},
        )

    @property
    def authorization_url(self) -> schema.Url:
        return self._oauth2.authorization_url

    @property
    def token_url(self) -> schema.Url:
        return self._oauth2.token_url

    @property
    def user_info_url(self) -> schema.Url | None:
        return self._oauth2.user_info_url

    @property
    def headers(self) -> dict[str, str]:
        return self._oauth2.headers

    @property
    def scopes(self) -> list[str]:
        return self._oauth2.scopes

    def redirect_for_authorization(
            self,
            target: schema.Url,
            *,
            prompt: _PROMPT_OPTIONS = None,  # common option for providers
    ) -> werkzeug.Response:
        """Redirect to GitHub OAuth2 authorization endpoint."""
        authsession = self.init_authsession(
            expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
            redirect_uri=_get_redirect_uri(),
            scopes=self._oauth2.scopes,
            target=target
        )
        url_params = {}
        if prompt:
            url_params["prompt"] = prompt
        authorization_url = self._oauth2.get_authorization_url(
            state=authsession.id,
            **url_params
        )
        return flask.redirect(authorization_url)

    def handle_callback(
            self,
            state: str,
            code: str,
            scope: str,
            **kwargs: str
    ) -> werkzeug.Response:
        authsession = self.get_authsession()
        self.validate_authsession(authsession, state)
        # Retrieve access token from GitHub
        # Fill in user info from userinfo endpoint
        token = self._oauth2.exchange_code_for_token(
            authsession=authsession,
            code=code,
            client_id=self._CLIENT_ID,  # type: ignore[arg-type]
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
        self.finalize_authsession(authsession)
        return flask.redirect(authsession.target or flask.request.host_url)
