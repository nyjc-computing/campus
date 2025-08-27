"""campus.client

Campus Client Package

Provides unified Campus client interface.
"""

from campus.client.config import get_app_base_url
from campus.client.core import Campus
from campus.client.errors import (
    CampusClientError,
    AuthenticationError,
    NetworkError
)
from campus.client.wrapper import ClientFactory, RequestsClient


def client_factory(app_name: str) -> ClientFactory:
    """Create a client factory for the given app.

    Args:
        app_name: Application name (e.g. campus.apps)

    Returns:
        ClientFactory: A factory for creating test clients
    """

    def wrapped_client_factory() -> RequestsClient:
        return RequestsClient(get_app_base_url(app_name))
    return wrapped_client_factory


__all__ = [
    'Campus',
    "ClientFactory",
    "client_factory",
    'CampusClientError',
    'AuthenticationError',
    'NetworkError',
]
