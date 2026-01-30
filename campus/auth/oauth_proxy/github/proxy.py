"""campus.auth.oauth_proxy.github.proxy

GitHub OAuth2 proxy implementation.
"""

__all__ = ["GitHubAuthProxy", "get_proxy"]

from typing import Literal

import flask
import werkzeug

from campus.common import env, schema, webauth
from campus.common.errors import auth_errors
import campus.config

from .. import base
from ... import resources

PROVIDER = "github"
REDIRECT_URI = schema.Url(env.HOSTNAME + f"/auth/{PROVIDER}/callback")
SCOPE_SEP = " "


def get_proxy() -> "GitHubAuthProxy":
    """Get an instance of the GitHubAuthProxy."""
    return GitHubAuthProxy()


class GitHubAuthProxy(base.AuthProxy):
    """GitHub OAuth2 provider implementation."""
    provider = PROVIDER
    title = "GitHub OAuth2 Authentication API"
    description = (
        "OAuth2 authentication endpoints for GitHub integration with Campus")
    version = "2022-11-28"
    openapi_version = "3.0.3"
    _oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
        provider=PROVIDER,
        client_id=env.CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        authorization_url=schema.Url(
            "https://github.com/login/oauth/authorize"),
        token_url=schema.Url(
            "https://github.com/login/oauth/access_token"),
        user_info_url=schema.Url("https://api.github.com/user"),
        scopes=["read:user", "read:email"],
        headers={"Accept": "application/json"},
    )
    _PROMPT_OPTIONS = Literal["select_account"] | None

    def __init__(self) -> None:
        super().__init__()

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
            prompt: _PROMPT_OPTIONS = None,
    ) -> werkzeug.Response:
        """Redirect to GitHub OAuth2 authorization endpoint."""
        authsession = self.init_authsession(
            expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
            redirect_uri=REDIRECT_URI,
            scopes=self._oauth2.scopes,
            target=target
        )
        authorization_url = self._oauth2.get_authorization_url(
            state=authsession.id,
            **{"prompt": prompt} if prompt else {}
        )
        return flask.redirect(authorization_url)

    def handle_callback(
            self,
            state: str,
            code: str,
            scope: str,
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
