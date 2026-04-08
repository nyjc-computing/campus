"""campus.auth.middleware

Middleware ("glue modules" to be used with deployments other than campus.auth)
- authenticate: Authenticate incoming requests using HTTP Basic/Bearer Authentication.
"""
from typing import Any, Callable, TypedDict

import flask

from campus import flask_campus
from campus.common import schema, webauth
from campus.common.errors import auth_errors


# Type stubs

# An authenticator returns a dict containing a client model and optionally a user model if authentication is successful.
# The return value must follow the format:
# {
    # "client": { ... },
    # "user": { ... }  # optional, only for bearer authentication
# }
class AuthResult(TypedDict):
    client: dict[str, Any]
    user: dict[str, Any] | None

# A basic authenticator takes in client_id and client_secret and raises an auth
# error if authentication fails
BasicAuthenticator = Callable[[str, str], dict[str, Any]]
# A bearer authenticator takes in an access token and raises an auth error if
# authentication fails
BearerAuthenticator = Callable[[str], dict[str, Any]]


class Authenticator:
    """Authenticator class for campus.auth.
    
    This class provides methods to authenticate credentials from:
    - client credentials (HTTP Basic Authentication)
    - access tokens (HTTP Bearer Authentication)
    """

    def __init__(
            self,
            basic_authenticator: BasicAuthenticator,
            bearer_authenticator: BearerAuthenticator,
    ):
        self._basic_authenticate = basic_authenticator
        self._bearer_authenticate = bearer_authenticator

    def authenticate(self) -> None:
        """Check request header for authorization credentials.

        Push credential information to flask.g for use in route
        handlers.
        """
        httpauth = webauth.http.HttpAuthenticationScheme.with_header(
            provider="campus",
            http_header=flask_campus.get_request_headers()
        )
        if not httpauth.header.authorization:
            raise auth_errors.InvalidRequestError(
                "Missing Authorization property in HTTP header"
            )
        match httpauth.scheme:
            case "basic":
                client_id, client_secret = (
                    httpauth.header.authorization.credentials()
                )
                auth_result = self._authenticate_basic(
                    schema.CampusID(client_id),
                    client_secret
                )
            case "bearer":
                access_token = httpauth.header.authorization.token
                auth_result = self._authenticate_bearer(access_token)
            case _:
                raise auth_errors.InvalidRequestError(
                    "Unsupported authentication scheme"
                )
        flask.g.current_client = auth_result.get("client")
        flask.g.current_user = auth_result.get("user")

    def _authenticate_basic(self, client_id: str, client_secret: str):
        """Authenticate using HTTP Basic Authentication."""
        return self._basic_authenticate(client_id, client_secret)
    
    def _authenticate_bearer(self, token: str):
        """Authenticate using HTTP Bearer Authentication."""
        return self._bearer_authenticate(token)
