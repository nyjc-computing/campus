"""campus.auth.oauth_proxy.google.proxy

Google OAuth2 proxy implementation.
"""

__all__ = ["GoogleAuthProxy", "get_proxy"]

from typing import Literal

import flask
import werkzeug

from campus.common import env, schema, webauth
from campus.common.errors import auth_errors, token_errors
import campus.config
import campus.model

from .. import base
from ... import resources

PROVIDER = "google"
REDIRECT_URI = schema.Url(f"https://{env.HOSTNAME}/auth/{PROVIDER}/callback")
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
    _PROMPT_OPTIONS = Literal[
        "consent",
        "login",
        "none",
        "select_account"
    ] | None
    
    def __init__(self) -> None:
        super().__init__()
        # Set OAuth2 scheme with credentials from vault (loaded in super().__init__)
        self._oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
            provider=PROVIDER,
            client_id=self._CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            authorization_url=schema.Url(
                "https://accounts.google.com/o/oauth2/v2/auth"
            ),
            token_url=schema.Url("https://oauth2.googleapis.com/token"),
            user_info_url=schema.Url(
                "https://www.googleapis.com/oauth2/v3/userinfo"
            ),
            scopes=[
                "email",
                "profile"
            ],
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
            hd: str | None = None,  # hosted domain
            login_hint: schema.Email | None = None,  # email hint
            prompt: _PROMPT_OPTIONS = None,
    ) -> werkzeug.Response:
        """Redirect to Google OAuth2 authorization endpoint."""
        import logging
        logger = logging.getLogger(__name__)
        
        authsession = self.init_authsession(
            expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
            redirect_uri=REDIRECT_URI,
            scopes=self._oauth2.scopes,
            target=target
        )
        
        # Build params dict
        # NOTE: Temporarily removed access_type and include_granted_scopes
        # as they may be triggering Google's v3 signin flow which returns 500 errors
        params = {}
        # params = {
        #     "access_type": "offline",
        #     "include_granted_scopes": "true",
        # }
        # NOTE: Temporarily commenting out hd to test with personal Google account
        # if hd:
        #     params["hd"] = hd
        if login_hint:
            params["login_hint"] = login_hint
        if prompt:
            params["prompt"] = prompt
            
        logger.info(f"[GOOGLE_OAUTH] Building authorization URL with params: {params}")
        logger.info(f"[GOOGLE_OAUTH] Session ID: {authsession.id}")
        logger.info(f"[GOOGLE_OAUTH] Redirect URI: {REDIRECT_URI}")
        logger.info(f"[GOOGLE_OAUTH] Scopes: {self._oauth2.scopes}")
        
        authorization_url = self._oauth2.get_authorization_url(
            state=authsession.id,
            **params
        )
        logger.info(f"[GOOGLE_OAUTH] Generated authorization URL: {authorization_url}")
        return flask.redirect(authorization_url)

    def handle_auth_callback(
            self,
            state: str,
            code: str,
            scope: str,
    ) -> campus.model.UserCredentials:
        """Handles Google OAuth callback for a consent flow

        Args:
            user_id: The user identifier
            client_id: The OAuth client ID
            token: The OAuthToken instance

        Returns:
            Updated UserCredentials instance
        """
        authsession = self.get_authsession()
        self.validate_authsession(authsession, state)
        # Retrieve access token from Google
        token = self._oauth2.exchange_code_for_token(
            authsession=authsession,
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
        # Fill in user info from userinfo endpoint
        userinfo = self._oauth2.get_user_info(token.access_token)
        user_id = schema.Email(userinfo["email"])
        # Verify domain is permitted
        if not user_id.domain == env.WORKSPACE_DOMAIN:
            raise token_errors.InvalidGrantError(
                f"Domain not allowed",
                domain=user_id.domain
            )
        # Store/update token
        credentials = resources.credentials[PROVIDER][user_id].update(
            client_id=self._CLIENT_ID,
            token=token,
        )
        # Update authsession with user_id before finalizing
        resources.session[PROVIDER][authsession.id].update(
            session_id=authsession.id,
            user_id=user_id
        )
        self.finalize_authsession(authsession)
        return credentials

    def handle_consent_callback(
            self,
            state: str,
            code: str,
            scope: str,
    ) -> werkzeug.Response:
        """Handles Google OAuth callback for a consent flow."""
        # handle_auth_callback() also retrieves authsession
        # Unfortunately this duplication of code is necessary because
        # handle_auth_callback will finalize the authsession, deleting
        # it from the store. So we get it here before that happens.
        authsession = self.get_authsession()
        self.handle_auth_callback(state, code, scope)
        return flask.redirect(authsession.target or flask.request.host_url)
