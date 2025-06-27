"""apps/api/models/campusauth

Authentication implementation for the Campus API.

This module handles authentication of credentials for Campus API requests.
"""

from functools import wraps
from typing import Callable

from flask import request
from flask.wrappers import Response

from apps.api.models.auth import http, oauth2

from apps.api.models.client import Client
from common.auth.header import HttpHeaderDict


basicauth = http.HttpAuthenticationScheme(
    security_scheme="http",
    scheme="basic",
    scopes=[]
)
bearerauth = http.HttpAuthenticationScheme(
    security_scheme="http",
    scheme="bearer",
    scopes=[]
)


def authenticate_client() -> tuple[Response, int] | None:
    """Authenticate the client using HTTP Basic Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    # Check for valid header
    basicauth.validate_header(request.headers)  # type: ignore[call-arg]
    auth_header = HttpHeaderDict(request.headers).get_auth()
    assert auth_header
    client_id, client_secret = auth_header.credentials()

    # Validate the client_id and client_secret
    client_model = Client()
    client_model.validate_credentials(client_id, client_secret)


def client_auth_required(func) -> Callable:
    """Decorator to enforce HTTP Basic Authentication."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> tuple[Response, int]:
        """Wrapper function that returns the error response from
        authentication, or calls the original function if authentication
        is successful.
        """
        return authenticate_client() or func(*args, **kwargs)

    return wrapper
