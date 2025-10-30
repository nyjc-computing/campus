"""campus.integrations.github

Provide functions and classes for Campus integration with GitHub.
"""

__all__ = ["GitHubProvider", "get_provider"]

from typing import Literal

import flask
import werkzeug

from campus.client.vault import get_vault
from campus.common import env, schema
from campus.common.errors import auth_errors
from campus.integrations import base
from campus.models import token, webauth

PROVIDER = "github"
REDIRECT_URI = schema.Url(env.HOSTNAME + f"/auth/{PROVIDER}/callback")
SCOPE_SEP = " "

tokens = token.Tokens()
vault = get_vault()[PROVIDER]


def get_provider() -> "GitHubProvider":
    """Get an instance of the GitHubProvider."""
    return GitHubProvider()

class GitHubProvider(base.Provider):
    """GitHub OAuth2 provider implementation."""
    provider = PROVIDER
    title = "GitHub OAuth2 Authentication API"
    description = ("OAuth2 authentication endpoints for GitHub integration with Campus")
    version = "2022-11-28"
    openapi_version = "3.0.3"
    authorization_url = schema.Url(
        "https://github.com/login/oauth/authorize"
    )
    token_url = schema.Url(
        "https://github.com/login/oauth/access_token"
    )
    user_info_url = schema.Url("https://api.github.com/user")
    _headers = {"Accept": "application/json"}
    _oauth2: webauth.oauth2.OAuth2AuthorizationCodeFlowScheme | None
    _PROMPT_OPTIONS = Literal["select_account"] | None

    def __init__(self) -> None:
        self._CLIENT_ID = vault["CLIENT_ID"].get()['value']
        self._CLIENT_SECRET = vault["CLIENT_SECRET"].get()['value']
        self._oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
            provider=PROVIDER,
            authorization_url=schema.Url(
                "https://github.com/login/oauth/authorize"),
            token_url=schema.Url(
                "https://github.com/login/oauth/access_token"),
            user_info_url=schema.Url("https://api.github.com/user"),
            scopes=["read:user", "read:email"],
            headers={"Accept": "application/json"},
        )

    def redirect_for_authorization(
            self,
            target: schema.Url,
            prompt: _PROMPT_OPTIONS = None,
    ) -> werkzeug.Response:
        """Redirect to GitHub OAuth2 authorization endpoint."""
        self._oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
            provider=PROVIDER,
            authorization_url=self.authorization_url,
            token_url=self.token_url,
            user_info_url=self.user_info_url,
            scopes=["read:user", "read:email"],
            headers=self._headers,
        )
        self._oauth2.init_session(
            redirect_uri=REDIRECT_URI,
            client_id=self._CLIENT_ID,
            scopes=self._oauth2.scopes,
            target=target
        )
        authorization_url = self._oauth2.get_authorization_url(
            **{"prompt": prompt} if prompt else {}
        )
        return flask.redirect(authorization_url)

    def handle_callback(
            self,
            state: str,
            code: str,
            scope: str,
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
         # Store token
        tokens.store(token)
        target = self._oauth2.auth_session.target
        self._oauth2.end_session()
        return flask.redirect(target or flask.request.host_url)
