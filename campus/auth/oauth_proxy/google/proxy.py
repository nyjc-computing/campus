"""campus.auth.oauth_proxy.google.proxy

Google OAuth2 proxy implementation.
"""

__all__ = ["GoogleAuthProxy", "get_proxy"]

from typing import Literal

import flask
import werkzeug

from campus.common import env, schema
from campus.common.errors import auth_errors, token_errors

from .. import base
from ... import resources, webauth

PROVIDER = "google"
REDIRECT_URI = schema.Url(env.HOSTNAME + f"/auth/{PROVIDER}/callback")
SCOPE_SEP = " "


def get_proxy() -> "GoogleAuthProxy":
    """Get an instance of the GoogleAuthProxy."""
    return GoogleAuthProxy()


class GoogleAuthProxy(base.AuthProxy):
    """Google OAuth2 provider implementation."""
    provider = PROVIDER
    title = "Google OAuth2 Authentication API"
    description = "OAuth2 authentication endpoints for Google integration with Campus"
    version = "2022-11-28"
    openapi_version = "3.0.3"
    _oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
        provider=PROVIDER,
        authorization_url=schema.Url(
            "https://accounts.google.com/o/oauth2/v2/auth"
        ),
        token_url=schema.Url("https://oauth2.googleapis.com/token"),
        user_info_url=schema.Url(
            "https://www.googleapis.com/oauth2/v3/userinfo"
        ),
        scopes=[
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile"
        ],
        headers={"Accept": "application/json"},
    )
    _PROMPT_OPTIONS = Literal[
        "consent",
        "login",
        "none",
        "select_account"
    ] | None

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
            *,
            hd: str | None = None,  # hosted domain
            login_hint: schema.Email | None = None,  # email hint
            prompt: _PROMPT_OPTIONS = None,
    ) -> werkzeug.Response:
        """Redirect to GitHub OAuth2 authorization endpoint."""

        self._oauth2.init_session(
            redirect_uri=REDIRECT_URI,
            client_id=self._CLIENT_ID,
            scopes=self._oauth2.scopes,
            target=target
        )
        authorization_url = self._oauth2.get_authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            **{"login_hint": login_hint} if login_hint else {},
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
        userinfo = self._oauth2.get_user_info(token.access_token)
        user_id = schema.Email(userinfo["email"])
        # Verify domain is permitted
        if not user_id.domain == env.WORKSPACE_DOMAIN:
            raise token_errors.InvalidGrantError(
                f"Domain not allowed",
                domain=user_id.domain
            )
        # Store/update token
        resources.credentials[PROVIDER][user_id].update(
            client_id=self._CLIENT_ID,
            token=token,
        )
        target = self._oauth2.finalize_session()
        return flask.redirect(target or flask.request.host_url)
