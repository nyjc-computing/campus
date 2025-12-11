"""campus.auth.oauth_proxy.campus.proxy

Campus OAuth2 proxy implementation.
"""

__all__ = ["CampusAuthProxy", "get_proxy"]

import flask
import werkzeug

from campus.common import env, schema, webauth
from campus.common.errors import api_errors, auth_errors, token_errors

from campus.campus.common.utils import url

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

    # Is this necessary? Campus apps should handle callback from provider
    def handle_callback(
            self,
            state: str,
            code: str,
            scope: str,
            **kwargs
    ) -> werkzeug.Response:
        authsession = self.get_authsession()
        assert authsession.user_id  # Updated by Campus OAuth provider
        requested_scopes = authsession.scopes
        # Exchange code for token; this will finalize auth_session
        token = self._oauth2.exchange_code_for_token(
            authsession=authsession,
            code=code,
            client_id=self._CLIENT_ID,
            client_secret=self._CLIENT_SECRET,
        )
        # Verify requested scopes were granted
        if missing_scopes := token.validate_scope(requested_scopes):
            raise auth_errors.InvalidScopeError(
                f"Missing required scopes: {', '.join(missing_scopes)}"
            )
        # Store/update token
        campus_cred_resource[authsession.user_id].update(
            client_id=self._CLIENT_ID,
            token=token,
        )
        self.finalize_authsession(authsession)
        # TODO: Expand target URL to include hostname if relative
        full_redirect_url = url.add_query(
            authsession.target or flask.request.host_url,
            **kwargs
        )
        return flask.redirect(full_redirect_url)
