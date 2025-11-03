"""campus.auth.routes

Flask blueprint modules for the auth service.

This package contains all HTTP route definitions organized by functionality:
- vault.py: Secret management operations (/vault/*)
- client.py: Client management operations (/client/*)

Each module defines a Flask blueprint with appropriate URL prefixes and
authentication decorators.
"""

__all__ = [
    "clients",
    "logins",
    "sessions",
    "users",
    "vaults",
]

import flask

from . import clients, credentials, logins, sessions, users, vaults
from .. import authentication


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialize the auth routes with the given Flask app or
    blueprint.
    """
    app.register_blueprint(clients.bp)
    app.register_blueprint(credentials.bp)
    app.register_blueprint(logins.bp)
    app.register_blueprint(sessions.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(vaults.bp)
    app.before_request(authentication.authenticate_client_from_request)
