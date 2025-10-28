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
from campus.common import schema
from campus.common.errors import api_errors
from campus.models import token, user, webauth

tokens = token.Tokens()
users = user.User()
vault = get_vault()


def authenticate_client(
        client_id: schema.CampusID,
        client_secret: str
) -> dict[str, str]:
    """Authenticate the client credentials against the vault.

    Args:
        client_id: The vault client ID
        client_secret: The vault client secret

    Returns:
        Client data dictionary if authentication is successful.

    Raises:
        UnauthorizedError: If authentication fails.
        InternalError: For other errors during authentication.
    """
    # Raised errors from this function should be handled by the caller
    auth_json = vault.clients.authenticate(
        client_id,
        client_secret
    )
    return auth_json


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
        .from_header(provider="campus", header=req_header)
        .get_auth(header=req_header)
    )
    match auth.scheme:
        case "basic":
            client_id, client_secret = auth.credentials()
            # Raises API errors if auth fails
            try:
                auth_json = authenticate_client(client_id, client_secret)
            except api_errors.NotFoundError:
                # Client ID not found means invalid credentials
                raise api_errors.UnauthorizedError(
                    "Invalid client credentials"
                )
            # Passthrough other errors
            if not auth_json["status"] == "success":
                raise api_errors.UnauthorizedError(
                    "Invalid client credentials"
                )
            flask.g.current_client = vault.clients.get(client_id)
        case "bearer":
            access_token = auth.value
            # raises UnauthorizedError for invalid access_token
            token = tokens.get(access_token)
            flask.g.current_user = users.get(token.user_id)
            flask.g.current_client = vault.client.get(token.client_id)
            flask.g.user_agent = request.headers.get("User-Agent", "")
            return {"message": "Bearer auth not implemented"}, 501


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


def get_client(client_id: schema.CampusID) -> dict[str, str] | None:
    """Retrieve a vault client by its client ID.

    Args:
        client_id: The vault client ID

    Returns:
        Client data dictionary, or None if not found
    """
    try:
        client = vault.clients.get(client_id)
    except api_errors.NotFoundError:
        return None
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    return client
