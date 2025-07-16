"""apps/campusauth/models

Authentication and authorisation implementation for the Campus API.

This module handles:
- authentication of credentials for Campus API requests.
- authorisation of requests based on access scopes.
"""

from functools import wraps
from typing import Callable

from flask import request

from campus.apps.campusauth.context import ctx
from campus.services.vault import client
from campus.apps.webauth import http


def authenticate_client() -> tuple[dict[str, str], int] | None:
    """Authenticate the client credentials using HTTP Basic Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    auth = (
        http.HttpAuthenticationScheme
        .from_header("campus", request.headers)
        .get_auth(request.headers)
    )
    match auth.scheme:
        case "basic":
            client_id, client_secret = auth.credentials()
            try:
                client.authenticate_client(client_id, client_secret)
                ctx.client = client.get_client(client_id)
            except client.ClientAuthenticationError:
                return {"message": "Invalid client credentials"}, 403
        case "bearer":
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
