"""campus.client

Campus Client Package

Provides unified Campus client interface.
"""

from flask import Flask

from campus.client.config import get_app_base_url
from campus.client.core import Campus
from campus.client.errors import (
    CampusClientError,
    AuthenticationError,
    NetworkError
)
from campus.client.wrapper import ClientFactory, RequestsClient


def client_factory(app: Flask) -> ClientFactory:
    """Create a client factory for the given Flask app.

    Args:
        app: Flask application instance

    Returns:
        ClientFactory: A factory for creating test clients
    """

    def wrapped_client_factory() -> RequestsClient:
        return RequestsClient(get_app_base_url(app))
    return wrapped_client_factory


__all__ = [
    'Campus',
    'CampusClientError',
    'AuthenticationError',
    'NetworkError',
]
