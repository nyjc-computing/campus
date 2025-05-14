from base64 import b64decode
from functools import wraps
from typing import Callable

from flask import g, request, jsonify
from flask.wrappers import Response

from apps.api.models.client import Client


def authenticate_client() -> tuple[Response, int] | None:
    """Authenticate the client using HTTP Basic Authentication.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return jsonify(
            {"message": "Missing or invalid Authorization header"}
        ), 401

    try:
        # Decode the Base64-encoded credentials
        encoded_credentials = auth_header.split(" ")[1]
        decoded_credentials = b64decode(encoded_credentials).decode("utf-8")
        client_id, client_secret = decoded_credentials.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return jsonify({"message": "Invalid credentials format"}), 401

    # Validate the client_id and client_secret
    client_model = Client()
    if not client_model.validate_credentials(client_id, client_secret):
        return jsonify({"message": "Invalid client_id or client_secret"}), 401
    
    # Store the client_id in Flask's g object for later use
    g.client_id = client_id


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
