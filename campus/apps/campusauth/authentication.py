"""campus.apps.campusauth.models

Authentication and authorisation implementation for the Campus API.

This module handles:
- authentication of credentials for Campus API requests.
- authorisation of requests based on access scopes.
"""

from functools import wraps
from typing import Callable

from flask import g, request

from campus.client import Campus
from campus.common.webauth import http
from campus.models.token import Tokens
from campus.models.user import User

tokens = Tokens()
users = User()


def authenticate_client() -> tuple[dict[str, str], int] | None:
    """Authenticate the client credentials using HTTP Basic Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    req_header = dict(request.headers)
    auth = (
        http.HttpAuthenticationScheme
        .from_header(provider="campus", header=req_header)
        .get_auth(header=req_header)
    )
    campus_client = Campus()
    match auth.scheme:
        case "basic":
            client_id, client_secret = auth.credentials()
            if not campus_client.vault.client.authenticate(
                client_id, client_secret
            ):
                return {"message": "Invalid client credentials"}, 403
            else:
                g.current_client = campus_client.vault.client.get(client_id)
        case "bearer":
            access_token = auth.value
            # raises UnauthorizedError for invalid access_token
            token = tokens.validate_token(access_token)
            g.current_user = users.get(token["user_id"])
            g.current_client = campus_client.vault.client.get(
                token["client_id"]
            )
            return {"message": "Bearer auth not implemented"}, 501


def client_auth_required(vf) -> Callable:
    """View function decorator to enforce HTTP Basic Authentication."""
    @wraps(vf)
    def authenticatedvf(*args, **kwargs):
        """Wrapper function that returns the error response from
        authentication, or calls the original function if authentication
        is successful.
        """
        return authenticate_client() or vf(*args, **kwargs)
    return authenticatedvf
