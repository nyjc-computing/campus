"""apps/campusauth/models

Authentication and authorisation implementation for the Campus API.

This module handles:
- authentication of credentials for Campus API requests.
- authorisation of requests based on access scopes.
"""

from functools import wraps
from typing import Callable

from flask import request
from flask.wrappers import Response

from apps.common.models.client import Client
from apps.common.webauth import http

basicauth = http.HttpAuthenticationScheme(
    provider="campus",
    security_scheme="http",
    scheme="basic",
)
bearerauth = http.HttpAuthenticationScheme(
    provider="campus",
    security_scheme="http",
    scheme="bearer",
)


def authenticate_client() -> tuple[Response, int] | None:
    """Authenticate the client credentials using HTTP Basic Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    # Check for valid header
    auth = basicauth.validate_header(request.headers)
    client_id, client_secret = auth.credentials()

    # Validate the client_id and client_secret
    Client().validate_credentials(client_id, client_secret)


def client_auth_required(vf) -> Callable:
    """View function decorator to enforce HTTP Basic Authentication."""
    @wraps(vf)
    def authenticatedvf(*args, **kwargs) -> tuple[Response, int]:
        """Wrapper function that returns the error response from
        authentication, or calls the original function if authentication
        is successful.
        """
        return authenticate_client() or vf(*args, **kwargs)

    return vf
