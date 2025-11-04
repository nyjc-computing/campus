"""campus.auth.authentication

Authentication and authorisation implementation for the Campus API.

This module handles:
- authentication of credentials for Campus API requests.
- authorisation of requests based on access scopes.
"""

from functools import wraps
from typing import Callable

import flask

from campus.common.errors import auth_errors
from campus.models import webauth

from . import resources


def authenticate_client_from_request() -> tuple[dict[str, str], int] | None:
    """Authenticate the client credentials using HTTP Basic/Bearer
    Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    req_header = dict(flask.request.headers)
    httpauth = (
        webauth.http.HttpAuthenticationScheme
        .from_header(provider="campus", http_header=req_header)
    )
    assert httpauth.header
    if not httpauth.header.authorization:
        raise auth_errors.InvalidRequestError(
            "Missing Authorization property in HTTP header"
        )
    match httpauth.scheme:
        case "basic":
            client_id, client_secret = (
                httpauth.header.authorization.credentials()
            )
            # Raises auth errors if auth fails
            resources.client.raise_for_authentication(client_id, client_secret)
            flask.g.current_client = resources.client[client_id].get()
        case "bearer":
            access_token = httpauth.header.authorization.token
            # raises UnauthorizedError for invalid access_token
            # TODO: use campus.auth.resources to retrieve token,
            # retrieve credentials
            credentials = resources.credentials["campus"].get(
                token_id=access_token
            )
            flask.g.current_user = (
                resources.user[credentials.user_id].get()
            )
            flask.g.current_client = (
                resources.client[credentials.client_id].get()
            )
            flask.g.user_agent = flask.request.headers.get("User-Agent", "")


def client_auth_required(vf) -> Callable:
    """View function decorator to enforce HTTP Basic Authentication."""
    @wraps(vf)
    def authenticatedvf(*args, **kwargs):
        """Wrapper function that returns the error response from
        authentication, or calls the original function if authentication
        is successful.
        """
        return (
            authenticate_client_from_request()
            or vf(*args, **kwargs)
        )
    return authenticatedvf
