"""campus.auth.oauth_proxy.google.proxy

Google OAuth2 proxy implementation.
"""

__all__ = ["GoogleAuthProxy", "get_proxy"]

from typing import Literal

import flask
import werkzeug

import campus.config
import campus.model
from campus.common import schema, webauth
from campus.common.errors import api_errors, auth_errors, token_errors
from campus.common.utils import url

from ... import get_yapper, integrations, resources, scopes
from .. import base

PROVIDER = "google"
SCOPE_SEP = " "


def _get_redirect_uri() -> schema.Url:
    """Get redirect URI with runtime env access."""
    return schema.Url(url.canonical_origin() + f"/auth/v1/{PROVIDER}/callback")


def get_proxy(
        integration: integrations.Integration | None = None,
) -> "GoogleAuthProxy":
    """Get an instance of the GoogleAuthProxy.

    Without an integration this is the identity/login proxy. With one,
    the proxy is bound to the integration's namespaced provider string:
    its vault label, authsession provider, Flask session key, credential
    keying and redirect URI all follow from it (#733).
    """
    return GoogleAuthProxy(integration)


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
    
    def __init__(
            self,
            integration: integrations.Integration | None = None,
    ) -> None:
        self.integration = integration
        self._config: integrations.IntegrationConfig | None = None
        if integration is not None:
            # Namespaced provider: the base class derives the vault
            # label, authsession provider and Flask session key from it.
            self.provider = integration.provider
            # Fail closed on an unconfigured integration here, before
            # the base class' plain vault reads turn a missing label
            # into an unhandled KeyError.
            self._config = integrations.get_config(integration)
        super().__init__()
        if integration is None:
            base_scopes = ["email", "profile"]
            redirect_uri = _get_redirect_uri()
        else:
            # The connect flow asks for exactly the vault SCOPES cap.
            base_scopes = self._config.scopes  # type: ignore[union-attr]
            redirect_uri = schema.Url(
                url.canonical_origin()
                + f"/auth/v1/{integration.base_provider}/{integration.slug}/callback"
            )
        self._redirect_uri = redirect_uri
        # Set OAuth2 scheme with credentials from vault (loaded in super().__init__)
        self._oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme(
            provider=self.provider,
            client_id=self._CLIENT_ID,
            redirect_uri=redirect_uri,
            authorization_url=schema.Url(
                "https://accounts.google.com/o/oauth2/v2/auth"
            ),
            token_url=schema.Url("https://oauth2.googleapis.com/token"),
            user_info_url=schema.Url(
                "https://www.googleapis.com/oauth2/v3/userinfo"
            ),
            scopes=base_scopes,
            headers={"Accept": "application/json"},
        )

    @property
    def connect_targets(self) -> tuple[str, ...]:
        """Origins the connect flow may redirect to (empty = disabled)."""
        if self._config is None:
            return ()
        return self._config.connect_targets

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

    def redirect_for_authorization(  # pyright: ignore [reportIncompatibleMethodOverride]
            self,
            target: schema.Url,
            *,
            hd: str | None = None,  # hosted domain
            login_hint: schema.Email | None = None,  # email hint
            prompt: _PROMPT_OPTIONS = None,
            extra_scopes: list[str] | None = None,
    ) -> werkzeug.Response:
        """Redirect to Google OAuth2 authorization endpoint.

        extra_scopes are merged on top of the proxy's base scopes
        (email, profile). Because include_granted_scopes=true is always
        sent, Google returns the cumulative scope set on re-consent, so
        the stored credential grows to the union — Campus's hosted
        incremental authorization for upstream providers (invariant B3,
        docs/auth-token-invariants.md). Callers cap extra_scopes
        upstream: provider.authorize validates against the requesting
        campus client's upstream_scopes allowlist.
        """
        merged_scopes = scopes.union(self._oauth2.scopes, extra_scopes or [])
        authsession = self.init_authsession(
            expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
            redirect_uri=self._redirect_uri,
            scopes=merged_scopes,
            target=target
        )

        # Build params dict
        params = {
            "access_type": "offline",
            "include_granted_scopes": "true",
        }
        if hd:
            params["hd"] = hd
        if login_hint:
            params["login_hint"] = login_hint
        if prompt:
            params["prompt"] = prompt

        authorization_url = self._oauth2.get_authorization_url(
            state=authsession.id,
            # get_authorization_url defaults to the scheme's fixed base
            # scopes; the merged set (base + extras) overrides it
            scope=" ".join(merged_scopes),
            **params
        )
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
        # Import env at runtime for WORKSPACE_DOMAIN access
        from campus.common import env
        authsession = self.get_authsession()
        self.validate_authsession(authsession, state)
        # Retrieve access token from Google
        token = self._oauth2.exchange_code_for_token(
            authsession=authsession,
            code=code,
            client_id=self._CLIENT_ID,  # type: ignore[arg-type]
            client_secret=self._CLIENT_SECRET,
        )
        # Verify requested scopes were granted. Google echoes the
        # cumulative scope set (include_granted_scopes=true); the
        # authsession's scopes are what this flow asked Google for, so
        # they must all be present in the grant (invariant B3).
        granted_scopes = scope.split(SCOPE_SEP)
        if missing_scopes := token.validate_scope(granted_scopes):
            raise auth_errors.InvalidScopeError(
                f"Missing required scopes: {', '.join(missing_scopes)}"
            )
        if missing_requested := (
            set(authsession.scopes) - set(granted_scopes)
        ):
            raise auth_errors.InvalidScopeError(
                f"Google grant missing requested scopes: "
                f"{', '.join(sorted(missing_requested))}",
                requested_scopes=authsession.scopes,
            )
        # Fill in user info from userinfo endpoint
        userinfo = self._oauth2.get_user_info(token.access_token)
        user_email = schema.Email(userinfo["email"])
        # Verify domain is permitted
        if not user_email.domain == env.WORKSPACE_DOMAIN:
            raise token_errors.InvalidGrantError(
                "Domain not allowed",
                domain=user_email.domain
            )
        user_id = schema.UserID(userinfo["email"])
        if self.integration is not None:
            self._validate_connect_binding(user_id, granted_scopes)
        # Store/update token
        credentials = resources.credentials[self.provider][user_id].update(
            client_id=self._CLIENT_ID,
            token=token,
        )
        # Update authsession with user_id before finalizing
        resources.session[self.provider][authsession.id].update(
            user_id=user_id
        )
        self.finalize_authsession(authsession)
        return credentials

    def _validate_connect_binding(
            self,
            user_id: schema.UserID,
            granted_scopes: list[str],
    ) -> None:
        """Enforce the connect flow's identity binding (design §2.3).

        The connect flow presumes the browser already holds a campus
        session from identity login, and the Google account that
        consents must be that same user — otherwise the credential
        would be stored for an identity that never authenticated here.
        Mirrors the classroom connect_from_callback rule. Runs before
        the credential is stored, so a mismatch stores nothing.
        """
        session_user = flask.session.get("user_id")
        if session_user is not None and session_user == str(user_id):
            return
        integration = self.integration
        assert integration is not None
        get_yapper().emit('campus.integrations.connect_fail', {
            "provider": integration.provider,
            "integration": integration.slug,
            "user_id": session_user,
            "google_user": str(user_id),
            "scopes": granted_scopes,
            "reason": (
                "consenting Google identity does not match the campus "
                "session user"
            ),
        })
        if session_user is None:
            raise api_errors.ForbiddenError(
                "Campus session required; sign in before connecting "
                "an integration"
            )
        raise api_errors.ForbiddenError(
            "The Google account that consented does not match the "
            f"signed-in user (session: {session_user}, "
            f"Google: {user_id})"
        )

    def handle_consent_callback(
            self,
            state: str,
            code: str,
            scope: str,
            **kwargs: str,
    ) -> werkzeug.Response:
        """Handles Google OAuth callback for a consent flow."""
        # handle_auth_callback() also retrieves authsession
        # Unfortunately this duplication of code is necessary because
        # handle_auth_callback will finalize the authsession, deleting
        # it from the store. So we get it here before that happens.
        authsession = self.get_authsession()
        # Finalize authsession and get credentials
        credentials = self.handle_auth_callback(state, code, scope)

        # Set Flask session for subsequent requests. The connect flow
        # binds to the session that started it (identity validated in
        # handle_auth_callback) and must not re-bind the session user;
        # it is the one that emits the connect audit event.
        session = flask.session
        if self.integration is not None:
            get_yapper().emit('campus.integrations.connect', {
                "provider": self.integration.provider,
                "integration": self.integration.slug,
                "user_id": str(credentials.user_id),
                "scopes": scope.split(SCOPE_SEP),
            })
        else:
            session['user_id'] = str(credentials.user_id)

        # Parse target URL and preserve existing query params (like state)
        from urllib.parse import parse_qs, urlparse
        target_url = authsession.target or url.canonical_origin()
        parsed = urlparse(target_url)
        existing_params = parse_qs(parsed.query)

        # Merge existing params (without user param - now in session)
        redirect_params = {**{k: v[0] for k, v in existing_params.items()}}

        # Redirect to target URL - user_id is now in the session
        redirect_url = url.add_query(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            **redirect_params
        )
        return flask.redirect(redirect_url)
