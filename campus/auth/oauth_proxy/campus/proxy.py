"""campus.auth.oauth_proxy.campus.proxy

Campus OAuth2 proxy implementation.
"""

__all__ = ["CampusAuthProxy", "get_proxy"]

import flask
import werkzeug

from campus.common import env, schema, webauth
from campus.common.utils import url

from .. import base
from ... import resources

PROVIDER = "campus"
# Assume campus proxy is hosted on same server as campus.auth
REDIRECT_URI = schema.Url("/auth/campus/callback")
SCOPE_SEP = " "

campus_cred_resource = resources.credentials[PROVIDER]
google_cred_resource = resources.credentials["google"]


def get_proxy() -> "CampusAuthProxy":
    """Get an instance of the CampusAuthProxy."""
    return CampusAuthProxy()


class CampusAuthProxy(base.AuthProxy):
    """Campus OAuth2 provider implementation."""
    provider = PROVIDER
    title = "Campus OAuth2 Authentication API"
    description = "OAuth2 authentication endpoints for Campus integration"
    version = "2025-11-05"
    openapi_version = "3.0.3"
    _oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
        client_id=env.CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        provider=PROVIDER,
        authorization_url=schema.Url(f"https://{env.HOSTNAME}/auth/v1/authorize"),
        token_url=schema.Url(f"https://{env.HOSTNAME}/auth/v1/token"),
        user_info_url=None,
        scopes=[
            "campus.profile",
            "campus.email",
        ],
        headers={"Accept": "application/json"},
    )

    def __init__(self) -> None:
        self._CLIENT_ID = env.CLIENT_ID
        self._CLIENT_SECRET = env.CLIENT_SECRET

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
            client_id: schema.CampusID,  # override
            state: str,  # auth session ID
            login_hint: schema.Email | None = None,  # email hint
    ) -> werkzeug.Response:
        """Redirect to Campus OAuth2 authorization endpoint."""
        # REMOVE: auth session already created in campus_python auth,authorize
        # authsession = self.init_authsession(
        #     expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
        #     redirect_uri=REDIRECT_URI,
        #     scopes=self._oauth2.scopes,
        #     target=target
        # )
        authorization_url = self._oauth2.get_authorization_url(
            # Ensure authsession ID is passed as state to callback
            redirect_uri=flask.url_for(".callback", state=state),
            client_id=client_id,
            state=state,
            **{"login_hint": login_hint} if login_hint else {},
        )
        return flask.redirect(authorization_url)

    # Campus apps handle their own token exchange (unlike external OAuth providers)
    def handle_callback(
            self,
            state: str,
            code: str,
            scope: str,
            **kwargs
    ) -> werkzeug.Response:
        # Retrieve session using state parameter (not Flask session)
        # Campus session created by campus_python, not stored in Flask session
        authsession = resources.session[PROVIDER][state].get()
        assert authsession.user_id  # Updated by Campus OAuth provider

        # NOTE: Do NOT exchange code for token here!
        # App (campus_python) exchanges code using its own credentials
        # We just redirect back to the app with code/state/scope

        # Redirect to app's target with authorization code
        # App will exchange code for token using its own client_id/secret
        full_redirect_url = url.add_query(
            authsession.target or flask.request.host_url,
            code=code,
            state=state,
            scope=scope,
            **kwargs
        )
        return flask.redirect(full_redirect_url)
