"""campus.auth.authentication

Authentication and authorisation implementation for the Campus API.

This module handles:
- authentication of credentials for Campus API requests.
- authorisation of requests based on access scopes.
"""

from functools import wraps
from typing import Callable

import flask

from campus.client.vault import get_vault
from campus.models import token, webauth

from . import resources

tokens = token.Tokens()
vault = get_vault()


def authenticate_client_from_request(
        request: flask.Request
) -> tuple[dict[str, str], int] | None:
    """Authenticate the client credentials using HTTP Basic
    Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    req_header = dict(request.headers)
    auth = (
        webauth.http.HttpAuthenticationScheme
        .from_header(provider="campus", http_header=req_header)
        .get_auth(http_header=req_header)
    )
    match auth.scheme:
        case "basic":
            client_id, client_secret = auth.credentials()
            # Raises auth errors if auth fails
            resources.client.authenticate(client_id, client_secret)
        case "bearer":
            access_token = auth.value
            # raises UnauthorizedError for invalid access_token
            # TODO: use campus.auth.resources to retrieve token,
            # retrieve credentials
            credentials = resources.credentials["campus"].get(
                token_id=access_token
            )
            flask.g.current_user = resources.user[
                credentials.user_id
            ].get()
            flask.g.current_client = (
                resources.client[credentials.client_id].get()
            )
            flask.g.user_agent = request.headers.get("User-Agent", "")


def client_auth_required(vf) -> Callable:
    """View function decorator to enforce HTTP Basic Authentication."""
    @wraps(vf)
    def authenticatedvf(*args, **kwargs):
        """Wrapper function that returns the error response from
        authentication, or calls the original function if authentication
        is successful.
        """
        return (
            authenticate_client_from_request(flask.request)
            or vf(*args, **kwargs)
        )
    return authenticatedvf
