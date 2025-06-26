from abc import ABC, abstractmethod
from functools import singledispatchmethod
from typing import Literal, NotRequired, TypedDict, Unpack
from urllib.parse import urlencode

import requests

AuthTypes = Literal["http", "apiKey", "oauth2", "openIdConnect"]
Url = str


class BaseAuthConfig(TypedDict):
    """Generalized authentication configuration.
    
    This base class defines a common structure for HTTP, API Key, OAuth2, and
    OpenID Connect authentication methods.
    The schema follows OpenAPI 3.0 for convenience
    https://swagger.io/docs/specification/v3_0/authentication/
    """
    type: AuthTypes  # Type of authentication method
    scopes: list[str]


class HttpAuthConfig(BaseAuthConfig):
    """HTTP authentication configuration.

    Limited to auth mechanisms supported by Campus, now or in future.
    """
    scheme: Literal["bearer"]  # Basic auth not supported


class ApiKeyAuthConfig(BaseAuthConfig):
    """API Key authentication configuration."""
    # Use 'in_' to avoid conflict with Python keyword
    in_: Literal["header", "query"]
    name: str  # Name of the header or query parameter


class OpenIdConnectAuthConfig(BaseAuthConfig):
    """OpenID Connect authentication configuration."""
    discovery_url: Url  # URL for OpenID Connect discovery document


class OAuth2BaseConfig(BaseAuthConfig):
    """OAuth2 base authentication configuration."""
    flow: Literal["authorizationCode", "clientCredentials", "implicit", "password"]
    # Optional, for additional parameters in requests


class OAuth2AuthorizationCodeConfig(OAuth2BaseConfig):
    """OAuth2 Authorization Code flow configuration."""
    authorization_url: Url  # Required for authorization code flow
    token_url: Url  # Required for token exchange
    user_info_url: NotRequired[Url]  # Optional, for user info endpoint
    extra_params: NotRequired[dict[str, str]]  # Optional, for additional parameters in requests
    token_params: NotRequired[dict[str, str]]  # Optional, for custom token exchange
    user_info_params: NotRequired[dict[str, str]]  # Optional, for custom


class OAuth2ClientCredentialsConfig(OAuth2BaseConfig):
    """OAuth2 Client Credentials flow configuration."""
    token_url: Url  # Required for token exchange
    extra_params: NotRequired[dict[str, str]]  # Optional, for additional parameters in requests
    token_params: NotRequired[dict[str, str]]  # Optional, for custom token exchange


class OAuth2ImplicitConfig(OAuth2BaseConfig):
    """OAuth2 Implicit flow configuration."""
    authorization_url: Url  # Required for implicit flow
    extra_params: NotRequired[dict[str, str]]  # Optional, for additional parameters in requests


class OAuth2PasswordConfig(OAuth2BaseConfig):
    """OAuth2 Password flow configuration."""
    token_url: Url  # Required for token exchange
    extra_params: NotRequired[dict[str, str]]  # Optional, for additional parameters in requests
    token_params: NotRequired[dict[str, str]]  # Optional, for custom token exchange


class AuthFlow(ABC):
    """Web auth model for authentication methods.

    Each authentication method and flow should inherit this subclass and
    implement its own required methods.
    """

    @abstractmethod
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @abstractmethod
    def get_auth_headers(self, *args) -> dict:
        """Return headers or params for authenticated requests."""
        pass

    @abstractmethod
    def is_authenticated(self, request) -> bool:
        """Check if authentication credentials are present in the request."""
        pass

    @abstractmethod
    def is_valid(self, request) -> bool:
        """Validate the authentication credentials in the request."""
        pass

    @singledispatchmethod
    @classmethod
    def from_json(cls, data: BaseAuthConfig) -> "AuthFlow":
        match data["type"]:
            # case "http":
            #     return HttpAuth(**data)
            # case "apiKey":
            #     return ApiKeyAuth(**data)
            case "oauth2":
                match data["flow"]:
                    case "authorizationCode":
                        return OAuth2AuthorizationCodeFlow(**data)
                    # case "clientCredentials":
                    #     return OAuth2ClientCredentials(**data)
                    # case "implicit":
                    #     return OAuth2Implicit(**data)
                    # case "password":
                    #     return OAuth2Password(**data)
                raise ValueError("Invalid OAuth2 flow type")
            # case "openIdConnect":
            #     return OpenIdConnectAuth(**data)
        raise ValueError(f"Unsupported auth type: {data['type']}")


# class HttpAuthFlow(WebAuth):
#     """Implements HTTP Bearer authentication flow.

#     Uses the Authorization header with a Bearer token for authentication.
#     """

#     def get_auth_headers(self, token: str) -> dict:
#         return {"Authorization": f"Bearer {token}"}

#     def is_authenticated(self, request) -> bool:
#         """Check if Bearer token is present in the Authorization header."""
#         auth_header = request.headers.get("Authorization", "")
#         return auth_header.startswith("Bearer ")

#     def is_valid(self, request) -> bool:
#         """Validate the Bearer token (stub, implement actual validation)."""
#         # Stub: Replace with actual token validation logic
#         return self.is_authenticated(request)


# class ApiKeyAuthFlow(WebAuth):
#     """Implements API Key authentication flow.

#     Supports API keys in HTTP headers or query parameters.
#     """

#     def get_auth_headers(self, api_key: str) -> dict:
#         if getattr(self, "in_", None) == "header":
#             return {self.name: api_key}
#         elif getattr(self, "in_", None) == "query":
#             return {"query": {self.name: api_key}}
#         return {}

#     def is_authenticated(self, request) -> bool:
#         """Check if API Key is present in the expected location."""
#         if getattr(self, "in_", None) == "header":
#             return self.name in request.headers
#         elif getattr(self, "in_", None) == "query":
#             return self.name in request.args
#         return False

#     def is_valid(self, request) -> bool:
#         """Validate the API Key (stub, implement actual validation)."""
#         # Stub: Replace with actual API key validation logic
#         return self.is_authenticated(request)


# class OpenIdConnectAuthFlow(WebAuth):
#     """Implements OpenID Connect authentication flow.

#     Uses OpenID Connect tokens and discovery document for authentication.
#     """

#     def get_auth_headers(self, token: str) -> dict:
#         return {"Authorization": f"Bearer {token}"}

#     def is_authenticated(self, request) -> bool:
#         """Check if OpenID Connect token is present in the Authorization header."""
#         auth_header = request.headers.get("Authorization", "")
#         return auth_header.startswith("Bearer ")

#     def is_valid(self, request) -> bool:
#         """Validate the OpenID Connect token (stub, implement actual validation)."""
#         # Stub: Replace with actual token validation logic
#         return self.is_authenticated(request)

#     def get_discovery_document(self) -> dict:
#         """Fetch and return the OpenID Connect discovery document."""
#         # Stub: In real implementation, fetch from self.discovery_url
#         return {}


class OAuth2AuthorizationCodeFlow(AuthFlow):
    """Implements OAuth2 Authorization Code flow.

    Uses a user-agent redirect to obtain an authorization code, then exchanges it for an access token.
    """

    def __init__(self, **kwargs: Unpack[OAuth2AuthorizationCodeConfig]):
        """Initialize with OAuth2 Authorization Code flow configuration."""
        super().__init__(**kwargs)
        self.scopes = kwargs["scopes"]
        self.authorization_url = kwargs["authorization_url"]
        self.token_url = kwargs["token_url"]
        self.user_info_url = kwargs.get("user_info_url", None)
        self.extra_params = kwargs.get("extra_params", {})
        self.token_params = kwargs.get("token_params", {})
        self.user_info_params = kwargs.get("user_info_params", {})

    def get_authorization_url(self, state: str, client_id: str, redirect_uri: str) -> str:
        """Return the authorization URL for redirect, with provider-specific params."""
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
        }
        params.update(getattr(self, "extra_params", {}) or {})
        base_url = getattr(self, "authorization_url", "")
        return f"{base_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, client_id: str, client_secret: str, redirect_uri: str, provider: str) -> dict:
        """Exchange authorization code for access token, with provider-specific params."""
        data = dict(
            grant_type="authorization_code",
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
            **self.token_params,
        )
        # Provider-specific tweaks
        if provider == "github":
            # GitHub expects params as JSON or form, and returns urlencoded by default
            headers = {"Accept": "application/json"}
        else:
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(self.token_url, data=data, headers=headers)
        try:
            return resp.json()
        except Exception:
            return {}

    def get_user_info(self, access_token: str) -> dict:
        """Fetch user info from the provider's user info endpoint."""
        if not self.user_info_url:
            return {}
        headers = self.get_auth_headers(access_token)
        headers.update(self.user_info_params)
        resp = requests.get(self.user_info_url, headers=headers)
        try:
            return resp.json()
        except Exception:
            return {}

    def get_auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def is_authenticated(self, request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        return auth_header.startswith("Bearer ")

    def is_valid(self, request) -> bool:
        # Stub: Replace with actual token validation logic
        return self.is_authenticated(request)


# class OAuth2ClientCredentialsFlow(WebAuth):
#     """Implements OAuth2 Client Credentials flow.

#     Obtains an access token using client credentials without user interaction.
#     """

#     def get_token(self) -> dict:
#         """Obtain access token using client credentials."""
#         # Stub: In real implementation, POST to self.token_url
#         return {}

#     def get_auth_headers(self, token: str) -> dict:
#         return {"Authorization": f"Bearer {token}"}

#     def is_authenticated(self, request) -> bool:
#         """Check if Bearer token is present in the Authorization header."""
#         auth_header = request.headers.get("Authorization", "")
#         return auth_header.startswith("Bearer ")

#     def is_valid(self, request) -> bool:
#         """Validate the Bearer token (stub, implement actual validation)."""
#         # Stub: Replace with actual token validation logic
#         return self.is_authenticated(request)


# class OAuth2ImplicitFlow(WebAuth):
#     """Implements OAuth2 Implicit flow.

#     Obtains an access token directly from the authorization endpoint via user-agent redirect.
#     """

#     def get_authorization_url(self, state: str) -> str:
#         """Return the authorization URL for implicit flow."""
#         # Stub: Compose URL from self.authorization_url and params
#         return getattr(self, "authorization_url", "")

#     def get_auth_headers(self, token: str) -> dict:
#         return {"Authorization": f"Bearer {token}"}

#     def is_authenticated(self, request) -> bool:
#         """Check if Bearer token is present in the Authorization header."""
#         auth_header = request.headers.get("Authorization", "")
#         return auth_header.startswith("Bearer ")

#     def is_valid(self, request) -> bool:
#         """Validate the Bearer token (stub, implement actual validation)."""
#         # Stub: Replace with actual token validation logic
#         return self.is_authenticated(request)


# class OAuth2PasswordFlow(WebAuth):
#     """Implements OAuth2 Resource Owner Password Credentials flow.

#     Obtains an access token using a username and password directly.
#     """

#     def get_token(self, username: str, password: str) -> dict:
#         """Obtain access token using username and password."""
#         # Stub: In real implementation, POST to self.token_url
#         return {}

#     def get_auth_headers(self, token: str) -> dict:
#         return {"Authorization": f"Bearer {token}"}

#     def is_authenticated(self, request) -> bool:
#         """Check if Bearer token is present in the Authorization header."""
#         auth_header = request.headers.get("Authorization", "")
#         return auth_header.startswith("Bearer ")

#     def is_valid(self, request) -> bool:
#         """Validate the Bearer token (stub, implement actual validation)."""
#         # Stub: Replace with actual token validation logic
#         return self.is_authenticated(request)
